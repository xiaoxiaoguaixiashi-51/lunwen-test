package com.example.service;

import com.example.repository.UserRepository;
import com.example.model.User;
import com.example.cache.CacheManager;
import com.example.event.EventPublisher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.LocalDateTime;
import java.util.Map;
import java.util.Optional;

/**
 * 示例：一个具有多种依赖的 Service 方法，用于验证 pipeline。
 * 依赖包括：外部 Repository、缓存、事件发布、日志、时间。
 */
public class UserService {

    private static final Logger logger = LoggerFactory.getLogger(UserService.class);

    private final UserRepository userRepository;
    private final CacheManager cacheManager;
    private final EventPublisher eventPublisher;

    public UserService(UserRepository userRepository, CacheManager cacheManager, EventPublisher eventPublisher) {
        this.userRepository = userRepository;
        this.cacheManager = cacheManager;
        this.eventPublisher = eventPublisher;
    }

    /**
     * 更新用户邮箱。
     * 依赖：UserRepository（数据库）、CacheManager（缓存失效）、EventPublisher（事件通知）、时间。
     */
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
            logger.info("Email unchanged for user {}", userId);
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

        logger.info("Updated email for user {} from {} to {}", userId, oldEmail, newEmail);
        return savedUser;
    }
}
