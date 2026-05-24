package com.example.plusbackend.controller;


import com.example.plusbackend.entity.Result;
import com.example.plusbackend.service.FileService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import javax.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;

@CrossOrigin(origins = "*")
@RestController
@RequestMapping("/file")
public class FileController {

    @Autowired
    FileService fileService;

    @GetMapping("/hello")
    public Result hello() {
        return Result.success();
    }

    @PostMapping("/upload")
    public String upload(@RequestParam("file") MultipartFile files) {
        return fileService.upload(files);
    }

    @PostMapping("/delete")
    public Result delete(@RequestBody List<String> filenames){
        return fileService.delete(filenames);
    }

    @GetMapping("/deleteAll")
    public Result deleteAll(){
        return fileService.deleteAll();
    }

    @GetMapping("/download")
    public Result download(HttpServletResponse response, @RequestParam("path") String path) throws IOException {
//        response.setContentType("application/force-download");// 设置强制下载不打开
        response.setContentType("application/octet-stream");

        return fileService.download(response, path);
    }
}
