package com.example.service;

import com.example.cache.CacheManager;
import com.example.event.EventPublisher;
import com.example.model.User;
import com.example.repository.UserRepository;

import java.time.LocalDateTime;
import java.util.Map;
import java.util.Optional;

public class UserService {
    private static final int MAX_FAILED_LOGIN_ATTEMPTS = 5;

    private final UserRepository userRepository;
    private final CacheManager cacheManager;
    private final EventPublisher eventPublisher;

    public UserService(UserRepository userRepository, CacheManager cacheManager, EventPublisher eventPublisher) {
        this.userRepository = userRepository;
        this.cacheManager = cacheManager;
        this.eventPublisher = eventPublisher;
    }

    public User updateUserEmail(Long userId, String newEmail) {
        if (newEmail == null || newEmail.isBlank()) {
            throw new IllegalArgumentException("Email cannot be blank");
        }

        Optional<User> optionalUser = userRepository.findById(userId);
        if (optionalUser.isEmpty()) {
            throw new RuntimeException("User not found: " + userId);
        }

        User user = optionalUser.get();
        String oldEmail = user.getEmail();

        if (oldEmail.equals(newEmail)) {
            return user;
        }

        if (userRepository.existsByEmail(newEmail)) {
            throw new IllegalStateException("Email already in use: " + newEmail);
        }

        user.setEmail(newEmail);
        user.setUpdatedAt(LocalDateTime.now());
        User savedUser = userRepository.save(user);

        cacheManager.evict("user:" + userId);
        eventPublisher.publish("user.email.changed", Map.of(
            "userId", userId,
            "oldEmail", oldEmail,
            "newEmail", newEmail
        ));

        return savedUser;
    }

    public User registerUser(String email, String displayName, String role) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email cannot be blank");
        }
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("Display name cannot be blank");
        }
        if (role == null || role.isBlank()) {
            role = "USER";
        }
        if (userRepository.existsByEmail(email)) {
            throw new IllegalStateException("Email already in use: " + email);
        }

        User user = new User(System.currentTimeMillis(), email);
        user.setDisplayName(displayName);
        user.setRole(role);
        user.setActive(true);
        user.setEmailVerified(false);
        user.setUpdatedAt(LocalDateTime.now());

        User savedUser = userRepository.save(user);
        cacheManager.evict("users:active");
        eventPublisher.publish("user.registered", Map.of(
            "userId", savedUser.getId(),
            "email", savedUser.getEmail(),
            "role", savedUser.getRole()
        ));
        return savedUser;
    }

    public User deactivateUser(Long userId, String reason) {
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("Deactivation reason is required");
        }

        User user = requireUser(userId);
        if (!user.isActive()) {
            return user;
        }
        if ("ADMIN".equals(user.getRole()) && userRepository.countActiveAdmins() <= 1) {
            throw new IllegalStateException("Cannot deactivate the last active admin");
        }

        user.setActive(false);
        user.setUpdatedAt(LocalDateTime.now());
        User savedUser = userRepository.save(user);

        cacheManager.evict("user:" + userId);
        cacheManager.evict("users:active");
        eventPublisher.publish("user.deactivated", Map.of(
            "userId", userId,
            "reason", reason,
            "deactivatedAt", savedUser.getUpdatedAt()
        ));
        return savedUser;
    }

    public User updateUserProfile(Long userId, String displayName, String requestedRole) {
        User user = requireUser(userId);
        String oldDisplayName = user.getDisplayName();
        String oldRole = user.getRole();

        if (displayName != null && !displayName.isBlank()) {
            user.setDisplayName(displayName);
        }
        if (requestedRole != null && !requestedRole.isBlank() && !requestedRole.equals(oldRole)) {
            if ("ADMIN".equals(requestedRole) && !userRepository.existsById(userId)) {
                throw new IllegalStateException("Cannot promote a non-persisted user");
            }
            user.setRole(requestedRole);
        }

        user.setUpdatedAt(LocalDateTime.now());
        User savedUser = userRepository.save(user);
        cacheManager.evict("user:" + userId);
        eventPublisher.publish("user.profile.updated", Map.of(
            "userId", userId,
            "oldDisplayName", oldDisplayName,
            "newDisplayName", savedUser.getDisplayName(),
            "oldRole", oldRole,
            "newRole", savedUser.getRole()
        ));
        return savedUser;
    }

    public User resetPasswordRequest(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email cannot be blank");
        }

        Optional<User> optionalUser = userRepository.findByEmail(email);
        if (optionalUser.isEmpty()) {
            throw new RuntimeException("User not found: " + email);
        }

        User user = optionalUser.get();
        if (!user.isActive()) {
            throw new IllegalStateException("Inactive users cannot reset password");
        }

        user.setUpdatedAt(LocalDateTime.now());
        User savedUser = userRepository.save(user);
        cacheManager.evict("password-reset:" + email);
        eventPublisher.publish("user.password.reset.requested", Map.of(
            "userId", savedUser.getId(),
            "email", email,
            "requestedAt", savedUser.getUpdatedAt()
        ));
        return savedUser;
    }

    public User verifyUserEmail(Long userId, String emailToken) {
        if (emailToken == null || emailToken.length() < 8) {
            throw new IllegalArgumentException("Invalid verification token");
        }

        User user = requireUser(userId);
        if (user.isEmailVerified()) {
            return user;
        }

        user.setEmailVerified(true);
        user.setUpdatedAt(LocalDateTime.now());
        User savedUser = userRepository.save(user);
        cacheManager.evict("user:" + userId);
        eventPublisher.publish("user.email.verified", Map.of(
            "userId", userId,
            "email", savedUser.getEmail(),
            "verifiedAt", savedUser.getUpdatedAt()
        ));
        return savedUser;
    }

    public User recordFailedLogin(Long userId, String sourceIp) {
        if (sourceIp == null || sourceIp.isBlank()) {
            throw new IllegalArgumentException("Source IP is required");
        }

        User user = requireUser(userId);
        int attempts = user.getFailedLoginAttempts() + 1;
        user.setFailedLoginAttempts(attempts);

        if (attempts >= MAX_FAILED_LOGIN_ATTEMPTS) {
            user.setActive(false);
            eventPublisher.publish("user.locked", Map.of(
                "userId", userId,
                "sourceIp", sourceIp,
                "attempts", attempts
            ));
        } else {
            eventPublisher.publish("user.login.failed", Map.of(
                "userId", userId,
                "sourceIp", sourceIp,
                "attempts", attempts
            ));
        }

        user.setUpdatedAt(LocalDateTime.now());
        User savedUser = userRepository.save(user);
        cacheManager.evict("user:" + userId);
        return savedUser;
    }

    public User reactivateUser(Long userId, String operatorRole) {
        if (!"ADMIN".equals(operatorRole)) {
            throw new IllegalStateException("Only admins can reactivate users");
        }

        User user = requireUser(userId);
        if (user.isActive()) {
            return user;
        }

        user.setActive(true);
        user.setFailedLoginAttempts(0);
        user.setUpdatedAt(LocalDateTime.now());
        User savedUser = userRepository.save(user);
        cacheManager.evict("user:" + userId);
        cacheManager.evict("users:active");
        eventPublisher.publish("user.reactivated", Map.of(
            "userId", userId,
            "operatorRole", operatorRole,
            "reactivatedAt", savedUser.getUpdatedAt()
        ));
        return savedUser;
    }

    public void deleteInactiveUser(Long userId, String operatorRole) {
        if (!"ADMIN".equals(operatorRole)) {
            throw new IllegalStateException("Only admins can delete users");
        }

        User user = requireUser(userId);
        if (user.isActive()) {
            throw new IllegalStateException("Active users cannot be deleted");
        }

        userRepository.delete(user);
        cacheManager.evict("user:" + userId);
        cacheManager.evict("users:active");
        eventPublisher.publish("user.deleted", Map.of(
            "userId", userId,
            "operatorRole", operatorRole,
            "deletedAt", LocalDateTime.now()
        ));
    }

    private User requireUser(Long userId) {
        Optional<User> optionalUser = userRepository.findById(userId);
        if (optionalUser.isEmpty()) {
            throw new RuntimeException("User not found: " + userId);
        }
        return optionalUser.get();
    }
}
