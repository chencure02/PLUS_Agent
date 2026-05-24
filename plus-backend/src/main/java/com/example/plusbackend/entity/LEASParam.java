package com.example.plusbackend.entity;

import lombok.Data;

import java.util.List;

@Data
public class LEASParam {
    String path;/*土地利用扩张数据  1.tiff*/

    String folder;/*驱动因子zip路径 factor.zip */

    int mtry;/*训练随机森林的特征数*/

    double rate;/*随机森林采样率*/

    int treeNum;/*决策树数目*/

    int threads;/*并行线程数*/
}
