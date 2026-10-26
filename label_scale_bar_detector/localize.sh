#!/bin/bash

cd label_scale_bar_detector/localizer/darknet/

# Set custom cfg to test mode
cd cfg
sed -i 's/^batch=.*/batch=1/' yolov4-obj.cfg
sed -i 's/^subdivisions=.*/subdivisions=1/' yolov4-obj.cfg
cd ..

# Remove result.json from previous run
rm -f result.json

# Run inference on images and save results as json
./darknet detector test data/obj.data cfg/yolov4-obj.cfg backup/yolov4-obj_best.weights -thresh 0.3 -i 0 -ext_output -dont_show -out result.json < data/test.txt

# Move back to project root
cd ../../../..
