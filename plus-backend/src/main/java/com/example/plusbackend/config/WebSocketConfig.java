package com.example.plusbackend.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.config.annotation.*;
import org.springframework.web.socket.server.standard.ServerEndpointExporter;

@CrossOrigin
@Configuration
@EnableWebSocketMessageBroker
// 通过 EnableWebSocketMessageBroker 开启使用 STOMP 协议来传输基于代理 (message broker) 的消息，此时浏览器支持使用 @MessageMapping 就像支持 @RequestMapping 一样。
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {
    /**
     * 添加一个服务端点，来接收客户端的连接
     * @param registry
     */
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws").setAllowedOriginPatterns("*").withSockJS();//.setAllowedOrigins("*")
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic");
    }

    /**
     * 开启WebSocket支持
     * @return
     */
    @Bean
    public ServerEndpointExporter serverEndpointExporter() {
        return new ServerEndpointExporter();
    }
}
