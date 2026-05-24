package com.example.plusbackend.service;

import com.example.plusbackend.entity.Result;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.io.FileUtils;
import org.jboss.netty.channel.ChannelHandler;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.multipart.MultipartFile;

import javax.servlet.http.HttpServletResponse;
import java.io.*;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@ChannelHandler.Sharable
public class FileService {

    public String upload(MultipartFile files) {
        try {
            File dir = new File("cpp/data");
            if (!dir.exists() && !dir.mkdir()) {
                return "400";
            }

            files.transferTo(new File(dir.getAbsolutePath() + File.separator + files.getOriginalFilename()));
            return "200";
        } catch (IOException e) {
            e.printStackTrace();
            return "400";
        }
    }

    public Result delete(List<String> filenames) {
        try {
            for (String filename : filenames) {
                File file = new File("cpp/data/" + filename);
                FileUtils.delete(file);
            }
            return Result.success();
        } catch (IOException e) {
            e.printStackTrace();
            return Result.error();
        }
    }

    public Result deleteAll() {
        /* 删除cpp/data与cpp/output目录下所有文件 */
        try {
            File dataDir = new File("cpp/data");
            File outputDir = new File("cpp/output");
            FileUtils.cleanDirectory(dataDir);
            FileUtils.cleanDirectory(outputDir);
            return Result.success();
        } catch (IOException e) {
            e.printStackTrace();
            return Result.error();
        }
    }

    public Result download(HttpServletResponse response, String path) throws IOException{
        List<File> files = new ArrayList<>();

        File file = new File(path);
        response.setCharacterEncoding("UTF-8");
        response.addHeader("Content-Length", "" + file.length());
        response.setStatus(HttpServletResponse.SC_OK);

        if (file.exists()) {
            response.addHeader("Content-Disposition", "attachment;filename=" + URLEncoder.encode(file.getName(), "UTF-8"));// 设置文件名

            byte[] buffer = FileUtils.readFileToByteArray(file);

            OutputStream outputStream = response.getOutputStream();
            outputStream.write(buffer);
            outputStream.flush();
        }
        return null;
    }
}
