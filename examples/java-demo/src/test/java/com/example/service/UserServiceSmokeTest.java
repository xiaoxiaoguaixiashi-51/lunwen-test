package com.example.service;

import com.example.cache.CacheManager;
import com.example.event.EventPublisher;
import com.example.model.User;
import com.example.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class UserServiceSmokeTest {
    @Mock
    private UserRepository userRepository;

    @Mock
    private CacheManager cacheManager;

    @Mock
    private EventPublisher eventPublisher;

    @Test
    void updateUserEmailUpdatesUserAndPublishesEvent() {
        User user = new User(1L, "old@example.com");
        UserService service = new UserService(userRepository, cacheManager, eventPublisher);

        when(userRepository.findById(1L)).thenReturn(Optional.of(user));
        when(userRepository.existsByEmail("new@example.com")).thenReturn(false);
        when(userRepository.save(user)).thenReturn(user);

        User result = service.updateUserEmail(1L, "new@example.com");

        assertEquals("new@example.com", result.getEmail());
        assertNotNull(result.getUpdatedAt());
        verify(cacheManager).evict("user:1");

        ArgumentCaptor<Map<String, Object>> payloadCaptor = ArgumentCaptor.forClass(Map.class);
        verify(eventPublisher).publish(eq("user.email.changed"), payloadCaptor.capture());
        assertEquals("old@example.com", payloadCaptor.getValue().get("oldEmail"));
        assertEquals("new@example.com", payloadCaptor.getValue().get("newEmail"));
    }
}
