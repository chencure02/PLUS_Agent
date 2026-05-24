package com.example.plusbackend.controller;

import com.example.plusbackend.entity.*;
import com.example.plusbackend.service.PlusService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@CrossOrigin(origins = "*")
@RestController
@RequestMapping("/plus")
public class PlusController {

    @Autowired
    PlusService plusService;

    @PostMapping("/convert")
    public Result convert(@RequestBody List<String> paths){
        return plusService.convert(paths);
    }

    @PostMapping("/linear")
    public Result linear(@RequestBody LinearParam linearParam){
        return plusService.linear(linearParam);
    }

    @PostMapping("/diverse")
    public Result diverse(@RequestBody List<String> paths){
        return plusService.diverse(paths);
    }

    @PostMapping("/markov")
    public Result markov(@RequestBody MarkovParam markovParam){
        return plusService.markov(markovParam);
    }

    @PostMapping("/leas")
    public Result leas(@RequestBody LEASParam leasParam){
        return plusService.leas(leasParam);
    }

    @PostMapping("/expansion")
    public Result expansion(@RequestBody List<String> paths){
        return plusService.expansion(paths);
    }

    @PostMapping("/cars")
    public Result cars(@RequestBody CARSParam carsParam){
        return plusService.cars(carsParam);
    }

    @PostMapping("/validate")
    public Result validate(@RequestBody ValidationParam validationParam){
        return plusService.validate(validationParam);
    }
}
