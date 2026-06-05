package com.example.event;

import java.util.Map;

public interface EventPublisher {
    void publish(String topic, Map<String, Object> payload);
}
