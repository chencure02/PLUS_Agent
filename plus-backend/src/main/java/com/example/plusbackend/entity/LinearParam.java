package com.example.plusbackend.entity;

import lombok.Data;

import java.util.List;

@Data
public class LinearParam {
    List<String> paths;

    int predictAmount;
}
