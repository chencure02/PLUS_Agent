package com.example.plusbackend.entity;

import lombok.Data;

import java.util.List;

@Data
public class CARSParam {

    String lulcPath; /* 土地利用扩张数据 lulc 1.tiff*/

    List<String> probabilityPath; /*概率tiff*/

    String policyPath; /*限制路径*/

    String outPath; /*输出路径 2.tiff*/

    int neighborSize; /*邻域大小*/

    int years; /*模拟年份*/

    int thread; /*线程数*/

    double patchGeneration; /*斑块生成阈值、递减阈值*/

    double expandCoefficient; /*扩散系数*/

    double percentageSeeds; /*随机种子最大比例*/

    List<Double> neighborWeight; /*邻域权重*/

    List<List<Integer>> matrix;/*转移矩阵*/

    List<List<Integer>> demands; /*年份 + 预期*/

    /* 颜色 */
    List<List<Integer>> colors;
}
