package com.example.plusbackend.entity;

import lombok.Data;

@Data
public class ValidationParam {
    boolean isFom;

    double rate;

    String simulatePath;

    String realPath;

    String startPath;
}
