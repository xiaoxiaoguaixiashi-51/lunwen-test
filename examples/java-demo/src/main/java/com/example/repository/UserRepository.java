package com.example.repository;

import com.example.model.User;
import java.util.Optional;

public interface UserRepository {
    Optional<User> findById(Long userId);

    boolean existsByEmail(String email);

    User save(User user);
}
