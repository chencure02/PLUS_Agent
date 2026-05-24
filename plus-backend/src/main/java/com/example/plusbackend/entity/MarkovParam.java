package com.example.plusbackend.entity;

import lombok.Data;

@Data
public class MarkovParam {

    /*开始年份的tiff路径*/
    String startPath;

    /*结束年份的tiff路径*/
    String endPath;

    /*开始年份*/
    int startYear;

    /*结束年份*/
    int endYear;

    /*预测年份*/
    int preYear;
}
