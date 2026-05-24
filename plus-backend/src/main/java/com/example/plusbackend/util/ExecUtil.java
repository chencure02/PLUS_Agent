package com.example.plusbackend.util;

import org.apache.commons.exec.*;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.io.ByteArrayOutputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;

@Component
public class ExecUtil {

    /**
     * make script file
     *
     * @param scriptFileName
     * @param content
     * @throws java.io.IOException
     */
    public static void markScriptFile(String scriptFileName, String content) throws Exception {
        // make file,   filePath/gluesource/666-123456789.py
        FileOutputStream fileOutputStream = null;
        try {
            fileOutputStream = new FileOutputStream(scriptFileName);
            fileOutputStream.write(content.getBytes("UTF-8"));
            fileOutputStream.close();
        } catch (Exception e) {
            throw e;
        } finally {
            if (fileOutputStream != null) {
                fileOutputStream.close();
            }
        }
    }

    /**
     * 日志文件输出方式
     * <p>
     * 优点：支持将目标数据实时输出到指定日志文件中去
     * 缺点：
     * 标准输出和错误输出优先级固定，可能和脚本中顺序不一致
     * Java 无法实时获取
     *
     * @param command
     * @param scriptFile
     * @param logFile
     * @param params
     * @return
     * @throws java.io.IOException
     */
    public static int execToFile(String command, String scriptFile, String logFile, String... params) throws IOException {
        // 标准输出：print （null if watchdog timeout）
        // 错误输出：logging + 异常 （still exists if watchdog timeout）
        // 标准输入
        FileOutputStream fileOutputStream = null;
        try {
            fileOutputStream = new FileOutputStream(logFile, true);
            PumpStreamHandler streamHandler = new PumpStreamHandler(fileOutputStream, fileOutputStream, null);
            int exitValue = execCmd(command, scriptFile, params, streamHandler);
            return exitValue;
        } catch (Exception e) {
            return -1;
        } finally {
            if (fileOutputStream != null) {
                try {
                    fileOutputStream.close();
                } catch (IOException e) {
                }
            }
        }
    }


    public static int execCmd(String command, String scriptFile, String[] params, PumpStreamHandler streamHandler) throws IOException {
        CommandLine commandline = new CommandLine(command);
        if (!StringUtils.isEmpty(scriptFile)) {
            commandline.addArgument(scriptFile);
        }
        if (params != null && params.length > 0) {
            commandline.addArguments(params);
        }
        //set watchdog
        ExecuteWatchdog watchdog = new ExecuteWatchdog(ExecuteWatchdog.INFINITE_TIMEOUT);
        // execCmd
        DefaultExecutor exec = new DefaultExecutor();
        exec.setWatchdog(watchdog);
        exec.setExitValues(null);
        exec.setStreamHandler(streamHandler);
        int exitValue = exec.execute(commandline);// exit code: 0=success, 1=error
        return exitValue;
    }

    public static String execToString(String command, String scriptFile, String... params) throws IOException {
        // 标准输出：print （null if watchdog timeout）
        // 错误输出：logging + 异常 （still exists if watchdog timeout）
        // 标准输入

        ByteArrayOutputStream outputStream = new ByteArrayOutputStream();

        try {
            PumpStreamHandler streamHandler = new PumpStreamHandler(outputStream, outputStream);
            execCmd(command, scriptFile, params, streamHandler);
        } catch (Exception e) {
            return null;
        } finally {
            try {
                outputStream.close();
            } catch (IOException e) {
                e.printStackTrace();
            }
        }
        return outputStream.toString("gbk");
    }

    public static CompletableFuture<Integer> execAsync(CommandLine commandLine, OutputStream out) throws IOException {

        PumpStreamHandler pumpStreamHandler = new PumpStreamHandler(out);
        DefaultExecutor executor = new DefaultExecutor();
        executor.setStreamHandler(pumpStreamHandler);

        /*异步任务*/
        CompletableFuture<Integer> cf = new CompletableFuture<>();
        // 创建DefaultExecuteResultHandler对象
        DefaultExecuteResultHandler resultHandler = new DefaultExecuteResultHandler() {
            @Override
            public void onProcessComplete(int exitValue) {
                // 将异步执行结果写入CompletableFuture对象
                cf.complete(exitValue);
            }

            @Override
            public void onProcessFailed(ExecuteException e) {
                // 将异常写入CompletableFuture对象
                cf.completeExceptionally(e);
            }
        };

        executor.execute(commandLine, resultHandler);

        return cf;
    }

    public static void execToStream(String command, String scriptFile, String... params) throws IOException {
        // 标准输出：print （null if watchdog timeout）
        // 错误输出：logging + 异常 （still exists if watchdog timeout）
        // 标准输入
        PumpStreamHandler streamHandler = new PumpStreamHandler(System.out, System.err);
        execCmd(command, scriptFile, params, streamHandler);
    }
}
