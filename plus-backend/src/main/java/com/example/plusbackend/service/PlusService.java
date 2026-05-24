package com.example.plusbackend.service;

import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.example.plusbackend.entity.*;
import com.example.plusbackend.util.ExecUtil;
import com.example.plusbackend.util.TifUtil;
import com.example.plusbackend.util.ZipUtils;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.exec.CommandLine;
import org.apache.commons.io.FileUtils;
import org.apache.logging.log4j.util.Base64Util;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.util.Base64Utils;

import javax.imageio.ImageIO;

import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.*;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Vector;
import java.util.concurrent.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
@Service
public class PlusService {
    @Autowired
    SimpMessagingTemplate simpMessagingTemplate;

    @Autowired
    TifUtil tifUtill;

    public Result convert(List<String> paths) {
        String txtString = "";

        txtString += "<Input number>\n";
        txtString += paths.size() + "\n";
        txtString += "<Input LULC series>\n";

        /* 写入input path */
        for (String path : paths) {
            txtString += "cpp/data/" + path + "\n";
        }

        txtString += "<Output LULC series>\n";

        /* 写入output path */
        for (String path : paths) {
            txtString += "cpp/output/" + path + "\n";
        }

        try {
            /* 写tmp文件 */
            FileUtils.write(new File("PLUS_Convert.tmp"), txtString, "utf8");

            /* 运行exe */
            String result = ExecUtil.execToString(".\\convert.bat", null);
            log.info(result);

            JSONObject jsonObject = new JSONObject();
            jsonObject.put("log", result);
            JSONArray outPathObject = new JSONArray();
            for (String path : paths) {
                outPathObject.add(path);
            }
            jsonObject.put("out_path", outPathObject);

            return Result.success(jsonObject);
        } catch (IOException e) {
            e.printStackTrace();
            return Result.error();
        }
    }

    public Result expansion(List<String> paths) {
        String txtString = "";

        txtString += "<Input number>\n";
        txtString += paths.size() + "\n";
        txtString += "<Input LULC series>\n";
        /* 写入input path */
        for (String path : paths) {
            txtString += "cpp/data/" + path + "\n";
        }
        txtString += "<Output change>\n";
        txtString += "cpp/output/expansion.tif\n";

        try {
            /* 写tmp文件 */
            FileUtils.write(new File("PLUS_Expansion.tmp"), txtString, "utf8");

            /* 运行exe */
            CommandLine command = CommandLine.parse(".\\expansion.bat");

            /* 管道输出 */
            PipedOutputStream pipedOutputStream = new PipedOutputStream();
            PipedInputStream pipedInputStream = new PipedInputStream(pipedOutputStream);
            BufferedReader bufferedReader = new BufferedReader(new InputStreamReader(pipedInputStream, "gbk"));

            ExecUtil.execAsync(command, pipedOutputStream).thenAccept(result -> {
                System.out.println("结束");
            });

            // 持续获取输出
            String line;
            while ((line = bufferedReader.readLine()) != null) {
                simpMessagingTemplate.convertAndSend("/topic/expansion", line);
            }

            // 关闭PipedOutputStream和BufferedReader
            pipedOutputStream.close();
            bufferedReader.close();
            ExecUtil.execAsync(command, null);

            JSONObject jsonObject = new JSONObject();
            // jsonObject.put("log", result);
            jsonObject.put("out_path", "expansion_landuse_1to2.tif");

            return Result.success(jsonObject);
        } catch (IOException e) {
            e.printStackTrace();
            return Result.error();
        }
    }

    public Result leas(LEASParam leasParam) {
        String txtString = "";
        String folderName = leasParam.getFolder();

        try {
            /* 解压缩驱动因子 */
            ZipUtils.decompress("cpp/data/" + folderName,
                    "cpp/data/" + folderName.substring(0, folderName.lastIndexOf(".")));

            txtString += "<Input LULC>\n";
            txtString += "cpp/data/" + leasParam.getPath() + "\n";

            txtString += "<InPut Featrue folder>\n";
            txtString += "cpp/data/" + folderName.substring(0, folderName.lastIndexOf(".")) + "/" + "\n";

            txtString += "<Output probability>\n";
            txtString += "cpp/output/" + leasParam.getPath() + "\n";

            txtString += "<Is net exit?>\n";
            txtString += "0\n";

            txtString += "<Input sampling rate>\n";
            txtString += leasParam.getRate() + "\n";

            txtString += "<mTry>\n";
            txtString += leasParam.getMtry() + "\n";

            txtString += "<Input the number of trees>\n";
            txtString += leasParam.getTreeNum() + "\n";

            txtString += "<Is balance?>\n";
            txtString += "0\n";

            txtString += "<Input thread count>\n";
            txtString += leasParam.getThreads() + "\n";

            txtString += "<High precision>\n";
            txtString += "0\n";
            txtString += "<Update Number>\n";
            txtString += "0\n";
            txtString += "<Update Variable>\n";
            txtString += "0\n";

            /* 写tmp文件 */
            FileUtils.write(new File("PLUS_LEAS.tmp"), txtString, "utf8");

            /* 运行exe */
            CommandLine command = CommandLine.parse(".\\leas.bat");

            /* 管道输出 */
            PipedOutputStream pipedOutputStream = new PipedOutputStream();
            PipedInputStream pipedInputStream = new PipedInputStream(pipedOutputStream);
            BufferedReader bufferedReader = new BufferedReader(new InputStreamReader(pipedInputStream, "gbk"));

            ExecUtil.execAsync(command, pipedOutputStream).thenAccept(result -> {
                System.out.println("结束");
            });

            // 持续获取输出
            String line;
            while ((line = bufferedReader.readLine()) != null) {
                simpMessagingTemplate.convertAndSend("/topic/leas", line);
            }

            // 关闭PipedOutputStream和BufferedReader
            pipedOutputStream.close();
            bufferedReader.close();
            ExecUtil.execAsync(command, null);

            /* 扫描outputPrefix开头的文件 */
            String outputPrefix = leasParam.getPath().substring(0, leasParam.getPath().lastIndexOf("."));

            File folder = new File("cpp/output/");
            File[] files = folder.listFiles((dir, name) -> name.startsWith(outputPrefix));
            JSONArray outPathObject = new JSONArray();
            for (File file : files) {
                String filename = file.getName();
                outPathObject.add(filename);
            }

            JSONObject jsonObject = new JSONObject();
            // jsonObject.put("log", result);
            jsonObject.put("out_path", outPathObject);

            return Result.success(jsonObject);
        } catch (Exception e) {
            e.printStackTrace();
            return Result.error();
        }
    }

    public Result linear(LinearParam linearParam) {
        String txtString = "";

        txtString += "<Image Amount>\n";
        txtString += linearParam.getPaths().size() + "\n";
        txtString += "<Predict Amount>\n";
        txtString += linearParam.getPredictAmount() + "\n";
        txtString += "<Images Path>\n";

        /* 写入input path */
        for (String path : linearParam.getPaths()) {
            txtString += "cpp/data/" + path + "\n";
        }

        try {
            /* 写tmp文件 */
            FileUtils.write(new File("PLUS_Linear.tmp"), txtString, "utf8");

            /* 运行exe */
            String result = ExecUtil.execToString(".\\linear.bat", null);
            log.info(result);

            JSONObject jsonObject = new JSONObject();
            jsonObject.put("log", result);

            return Result.success(jsonObject);
        } catch (IOException e) {
            e.printStackTrace();
            return Result.error();
        }
    }

    public Result diverse(List<String> paths) {
        String txtString = "";

        txtString += "<Image Amount>\n";
        txtString += paths.size() + "\n";
        txtString += "<Images Path>\n";

        /* 写入input path */
        for (String path : paths) {
            txtString += "cpp/data/" + path + "\n";
        }

        txtString += "<Output Path>\n";

        /* 写入output path */
        String outputPath = "LULCs.tif";
        txtString += "cpp/output/" + outputPath + "\n";

        try {
            /* 写tmp文件 */
            FileUtils.write(new File("PLUS_Diverse.tmp"), txtString, "utf8");

            /* 运行exe */
            String result = ExecUtil.execToString(".\\diverse.bat", null);
            log.info(result);

            JSONObject jsonObject = new JSONObject();
            jsonObject.put("log", result);
            JSONArray outPathObject = new JSONArray();
            outPathObject.add(outputPath);
            jsonObject.put("out_path", outPathObject);

            return Result.success(jsonObject);
        } catch (IOException e) {
            e.printStackTrace();
            return Result.error();
        }
    }

    public Result markov(MarkovParam markovParam) {
        String txtString = "";

        txtString += "<StartMap>\n";
        txtString += "cpp/data/" + markovParam.getStartPath() + "\n";
        txtString += "<EndMap>\n";
        txtString += "cpp/data/" + markovParam.getEndPath() + "\n";
        txtString += "<Start Year>\n";
        txtString += markovParam.getStartYear() + "\n";
        txtString += "<End Year>\n";
        txtString += markovParam.getEndYear() + "\n";

        txtString += "<Predict Year>\n";
        txtString += markovParam.getPreYear() + "\n";

        try {
            /* 写tmp文件 */
            FileUtils.write(new File("PLUS_Markov.tmp"), txtString, "utf8");

            /* 运行exe */
            String result = ExecUtil.execToString(".\\markov.bat", null);
            log.info(result);

            JSONObject jsonObject = new JSONObject();
            jsonObject.put("log", result);
            JSONArray outPathObject = new JSONArray();
            outPathObject.add("markov.csv");
            jsonObject.put("out_path", outPathObject);

            return Result.success(jsonObject);
        } catch (IOException e) {
            e.printStackTrace();
            return Result.error();
        }
    }

    public Result cars(CARSParam carsParam) {
        String txtString = "";

        /* classes */
        txtString += "<Input classes>\n";
        txtString += carsParam.getProbabilityPath().size() + "\n";

        /* lulc tiff */
        txtString += "<Input LULC>\n";
        txtString += "cpp/data/" + carsParam.getLulcPath() + "\n";

        /* 概率tiff */
        txtString += "<Input Probability Folder>\n";
        for (String path : carsParam.getProbabilityPath()) {
            txtString += "cpp/data/" + path + "\n";
        }

        /* 输出tiff */
        txtString += "<Output simulation>\n";
        txtString += "cpp/output/" + carsParam.getOutPath() + "\n";

        /* 限制tiff */
        txtString += "<Input Policy>\n";
        if (carsParam.getPolicyPath() == null || carsParam.getPolicyPath().equals("")) {
            txtString += "\n";
        } else {
            txtString += "cpp/data/" + carsParam.getPolicyPath() + "\n";
        }

        /* 邻域大小 */
        txtString += "<Input Neighborhood>\n";
        txtString += carsParam.getNeighborSize() + "\n";

        /* 预测年份 */
        txtString += "<How many years>\n";
        txtString += carsParam.getYears() + "\n";

        /* 线程数 */
        txtString += "<Input thread count>\n";
        txtString += carsParam.getThread() + "\n";

        /* 斑块生长阈值 */
        txtString += "<Patch generation>\n";
        txtString += carsParam.getPatchGeneration() + "\n";

        /* 扩散系数 */
        txtString += "<Expansion coefficient>\n";
        txtString += carsParam.getExpandCoefficient() + "\n";

        /* 邻域权重 */
        txtString += "<Neighborhood Weight>\n";
        /* 中间逗号分隔 */
        for (int i = 0; i < carsParam.getNeighborWeight().size(); i++) {
            txtString += carsParam.getNeighborWeight().get(i);
            if (i != carsParam.getNeighborWeight().size() - 1) {
                txtString += ",";
            }
        }
        txtString += "\n";

        /* 转移矩阵 */
        txtString += "<Transition matrix>\n";
        /* 中间逗号分隔 */
        for (int i = 0; i < carsParam.getMatrix().size(); i++) {
            for (int j = 0; j < carsParam.getMatrix().get(i).size(); j++) {
                txtString += carsParam.getMatrix().get(i).get(j);
                if (j != carsParam.getMatrix().get(i).size() - 1) {
                    txtString += ",";
                } else {
                    txtString += "\n";
                }
            }
        }

        /* 年份 + 预期目标 */
        txtString += "<Years and corresponding demands>\n";
        /* 中间逗号分隔 */
        for (int i = 0; i < carsParam.getDemands().size(); i++) {
            for (int j = 0; j < carsParam.getDemands().get(i).size(); j++) {
                txtString += carsParam.getDemands().get(i).get(j);
                if (j != carsParam.getDemands().get(i).size() - 1) {
                    txtString += ",";
                } else {
                    txtString += "\n";
                }
            }
        }

        /* 随机种子最大比例 */
        txtString += "<Percentage of seeds>\n";
        /* double去掉e */
        txtString += new BigDecimal(carsParam.getPercentageSeeds() + "") + "\n";

        txtString += "<Development type exist>\n";
        txtString += "0\n";
        txtString += "<Development type>\n";
        txtString += "0\n";
        txtString += "<Development weight>\n";
        txtString += "0.5\n";

        try {
            ExecutorService executor = new ThreadPoolExecutor(4, 10,
                    60L, TimeUnit.SECONDS, new SynchronousQueue<>());

            /* 写tmp文件 */
            FileUtils.write(new File("PLUS_CARS.tmp"), txtString, "utf8");

            /* 运行exe */
            CommandLine command = CommandLine.parse(".\\cars.bat");

            /* 管道输出 */
            PipedOutputStream pipedOutputStream = new PipedOutputStream();
            PipedInputStream pipedInputStream = new PipedInputStream(pipedOutputStream);
            BufferedReader bufferedReader = new BufferedReader(new InputStreamReader(pipedInputStream));

            ExecUtil.execAsync(command, pipedOutputStream).thenAccept(result -> {
                System.out.println("结束");
            });


            /* 随机生成12种颜色 */
            Vector<Color> colors = new Vector<>();
            colors.add(new Color(255, 255, 255));
            for (int i = 0; i < 12; i++) {
                colors.add(new Color((int) (Math.random() * 255),
                        (int) (Math.random() * 255),
                        (int) (Math.random() * 255)));
            }
            // 持续获取输出
            String line;
            while ((line = bufferedReader.readLine()) != null) {
                simpMessagingTemplate.convertAndSend("/topic/cars", line);
                /*
                 * 获取Count Pixel: 1 - 43402 269416 2312089 1096722 33839 1431466
                 * 139135的正则,第一个数为轮次，后面的数不定长，存入list
                 */
                Pattern pattern = Pattern.compile("Count Pixel: (\\d+) - (.*)");
                Matcher matcher = pattern.matcher(line);
                if (matcher.find()) {
                    if (matcher.group(2).trim().equals("")) {
                        continue;
                    }
                    String[] split = matcher.group(2).split(" ");
                    List<Integer> list = new ArrayList<>();
                    for (String s : split) {
                        list.add(Integer.parseInt(s));
                    }
                    JSONObject jsonObject = new JSONObject();
                    jsonObject.put("iteration", Integer.parseInt(matcher.group(1)));
                    jsonObject.put("data", list);
                    simpMessagingTemplate.convertAndSend("/topic/cars_iteration", jsonObject);

                    /* 检查cpp/output/下前缀为outpath的tiff文件，转换为png */
                    File directory = new File("cpp/output");
                    File[] files = directory.listFiles();
                    String tmpPath = carsParam.getOutPath().substring(0, carsParam.getOutPath().lastIndexOf("."));
                    for (File f : files) {
                        if (f.getName().startsWith(tmpPath)) {
                            executor.execute(() -> {
                                try {
                                    // File file = new File("cpp/output/" + f.getName());

//                                    /* 从colors中解析颜色 */
//                                    Vector<Color> colors = new Vector<>();
//                                    for (int i = 0; i < carsParam.getColors().size(); i++) {
//                                        colors.add(new Color(carsParam.getColors().get(i).get(0),
//                                                carsParam.getColors().get(i).get(1),
//                                                carsParam.getColors().get(i).get(2)));
//                                    }


                                    /* tif转彩色png */
                                    TifUtil.colorTif("cpp/output/" + f.getName(), "tmp.png", colors);
                                    // tifUtill("cpp/output/" + f.getName(), "tmp.png",colors);

                                    // BufferedImage bufferedImage = ImageIO.read(file);
                                    // String pngName = "tmp.png";
                                    // ImageIO.write(bufferedImage, "png", new File("cpp/output/" + pngName));
                                } catch (Exception e) {
                                    e.printStackTrace();
                                }
                            });
                        }
                    }
                }
            }

            // 关闭PipedOutputStream和BufferedReader
            pipedOutputStream.close();
            bufferedReader.close();
            ExecUtil.execAsync(command, null);

            /* 返回 */
            JSONObject jsonObject = new JSONObject();
            JSONArray outPathObject = new JSONArray();
            outPathObject.add("outputSimulation_1.tif");
            jsonObject.put("out_path", outPathObject);
            // jsonObject.put("log", result);

            return Result.success(jsonObject);
        } catch (Exception e) {
            e.printStackTrace();
            return Result.error();
        }
    }


    public Result validate(ValidationParam validationParam) {
        String txtString = "";

        txtString += "<IsFom>\n";
        txtString += validationParam.isFom() + "\n";


        txtString += "<Sampling rate>\n";
        txtString += validationParam.getRate() + "\n";

        txtString += "<Simulated Map>\n";
        txtString += "cpp/data/" + validationParam.getSimulatePath() + "\n";

        txtString += "<Real Map>\n";
        txtString += "cpp/data/" + validationParam.getRealPath() + "\n";

        txtString += "<Start Map>\n";
        txtString += "cpp/data/" + validationParam.getStartPath() + "\n";

        try {
            FileUtils.write(new File("PLUS_Validation.tmp"), txtString, "utf8");

            /* 运行exe */
            String result = ExecUtil.execToString(".\\validate.bat", null);

            /* 返回 */
            JSONObject jsonObject = new JSONObject();
            JSONArray outPathObject = new JSONArray();
            if (validationParam.isFom())
                outPathObject.add("FoM.csv");
            else
                outPathObject.add("Kappa.csv");
            jsonObject.put("out_path", outPathObject);
            jsonObject.put("log", result);

            return Result.success(jsonObject);
        } catch (Exception e) {
            e.printStackTrace();
            return Result.error();
        }
    }
}
