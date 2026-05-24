package com.example.plusbackend.entity;

import lombok.AllArgsConstructor;
import lombok.Data;

@AllArgsConstructor
@Data
public class Result<T> {

    private int code;

    private String msg = "success";

    private T data;

    public Result(int code,String msg){
        this.code = code;
        this.msg = msg;
    }

    public static Result success(){
        return new Result(200, "success");
    }

    public static Result success(String msg){
        return new Result(200, msg);
    }

    public static Result success(Object object){
        return new Result(200, "success",object);
    }

    public static Result error(){
        return new Result(400, "error");
    }
}



