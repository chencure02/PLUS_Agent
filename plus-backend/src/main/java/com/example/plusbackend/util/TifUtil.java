package com.example.plusbackend.util;


import org.springframework.stereotype.Component;

import javax.imageio.ImageIO;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.File;
import java.io.IOException;
import java.util.Vector;

@Component
public class TifUtil {
    public static void colorTif(String tifPath, String pngPath, Vector<Color> colors) {
        try {
            // 读取灰度图像
            BufferedImage grayImage = ImageIO.read(new File(tifPath));

            // 创建新的RGB图像
            BufferedImage rgbImage = new BufferedImage(grayImage.getWidth(), grayImage.getHeight(),
                    BufferedImage.TYPE_INT_RGB);

            /* 输入n种RGB颜色，将图中颜色转变为这n种颜色,png也只有n种颜色 */
            Vector<Integer> grayColors = new Vector<Integer>();

            for (int y = 0; y < grayImage.getHeight(); y++) {
                for (int x = 0; x < grayImage.getWidth(); x++) {
                    // 加入到vector中，如果已经存在，就不加入
                    Color color = new Color(grayImage.getRGB(x, y));
                    if (!grayColors.contains(color.getRGB())) {
                        grayColors.add(color.getRGB());
                    }
                }
            }

            // 再次遍历，将颜色转换为n种颜色
            for (int y = 0; y < grayImage.getHeight(); y++) {
                for (int x = 0; x < grayImage.getWidth(); x++) {
                    Color color = new Color(grayImage.getRGB(x, y));
                    int index = grayColors.indexOf(color.getRGB());
                    rgbImage.setRGB(x, y, colors.get(index).getRGB());
                }
            }

            // 保存彩色图像
            File output = new File(pngPath);
            ImageIO.write(rgbImage, "png", output);
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}
