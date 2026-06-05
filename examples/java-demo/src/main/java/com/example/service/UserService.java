package com.example.service;

import com.example.cache.CacheManager;
import com.example.event.EventPublisher;
import com.example.model.User;
import com.example.repository.UserRepository;

import java.time.LocalDateTime;
import java.util.Map;
import java.util.Optional;

public class UserService {
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
}
