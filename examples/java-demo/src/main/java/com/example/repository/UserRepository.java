package com.example.repository;

import com.example.model.User;
import java.util.Optional;

public interface UserRepository {
    Optional<User> findById(Long userId);

    Optional<User> findByEmail(String email);

    boolean existsByEmail(String email);

    boolean existsById(Long userId);

    long countActiveAdmins();

    User save(User user);

    void delete(User user);
}
