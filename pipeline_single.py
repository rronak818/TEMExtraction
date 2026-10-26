import os
import re
import time
import urllib.request
import torch
import shutil
import subprocess
import pandas as pd
from PIL import Image

from figure_separator import extract
from ImageSoup import extract_figures_single_paper
from classifier import classify
from torchvision import datasets
from label_scale_bar_detector.localizer import detect, GPU_on, GPU_off
from utils import (ImageExtractor, image_extractor, gif_to_jpg, crop_images, crop_labels, crop_scales,
                read_OCR_from_folder, run_segmentation, measure_bars, drop_zeros)


def load_html_source(source):
    if source.startswith("http://") or source.startswith("https://"):
        request = urllib.request.Request(
            source,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urllib.request.urlopen(request) as response:
            return response.read().decode("utf-8", errors="ignore")

    with open(source, "r", encoding="utf-8") as f:
        return f.read()


def run_pipeline_single(
    output_dir,
    gpu,
    publisher,
    html_source,
    doi=None,
    year=None,
    pdf_path=None,
    input_image=None
):

    # Set GPU option in the Makefile of label_scale_bar_detector
    if gpu:
        GPU_on()
    else:
        GPU_off()

    def make_path(path):
        return os.path.join(output_dir, path)

    def create_dir(path):
        if not os.path.isdir(path):
            os.makedirs(path)

    create_dir(output_dir)

    if input_image:
        if not os.path.isfile(input_image):
            raise ValueError("Input image does not exist: {}".format(input_image))

        # Normalize the selected image for downstream model compatibility.
        create_dir(make_path("TEM"))
        image_name = os.path.splitext(os.path.basename(input_image))[0] + ".jpg"
        image_output_path = make_path(os.path.join("TEM", image_name))

        with Image.open(input_image) as image:
            image.convert("RGB").save(image_output_path, format="JPEG")

        print("Manual image prepared:", image_output_path)

    else:
        # Extract images from htmls
        html_content = load_html_source(html_source)

        if publisher == "nature":
            meta = extract_figures_single_paper(
                publisher,
                html_content,
                DOI=doi,
                year=year
            )
        elif publisher == "springer":
            meta = extract_figures_single_paper(
                publisher,
                html_content,
                pdf_path=pdf_path
            )
        else:
            meta = extract_figures_single_paper(
                publisher,
                html_content
            )

        # publishers = ["Elsevier", "Nature Publishing Group", "The Royal Society of Chemistry", "Springer"]
        # # Extract images
        # for publisher in publishers:
        #     image_extractor.extract(publisher, download=True)
        # create_dir(make_path('extracted_images_gif'))
        run_image_extractor = ImageExtractor(make_path("extracted_images_gif"))
        run_image_extractor.extract_single_paper(publisher, meta)

        # Convert from gif to jpg
        # if not os.path.isdir(make_path("extracted_images_jpg")):
        #     os.mkdir(make_path("extracted_images_jpg"))
        for f in os.listdir(make_path("extracted_images_gif")):
            create_dir(os.path.join(make_path('extracted_images_jpg')))
            gif_to_jpg(os.path.join(make_path("extracted_images_gif"), f),
                    os.path.join(make_path("extracted_images_jpg"), str(f) + ".jpg"))

        # Separate subfigures from composite figures
        extract(make_path('extracted_images_jpg'), output_dir)
        crop_images(make_path("extracted_images_jpg"), make_path("extracted_subfigures_json"), make_path("extracted_subfigures_png"))

        classify(make_path('extracted_subfigures_png'), 'sem_tem_other', output_dir, False)

    # # Classify subfigures into TEM, XRD, Other
    # classify(make_path('extracted_subfigures_png'), 'tem_xrd_other', output_dir, GPU)

    # # Classify TEM images into subcategories
    # classify(make_path('TEM'), 'tem_subcategories', output_dir, GPU)

    # Classify TEM images into Particulate and Non-particulate
    classify(make_path('TEM'), 'particulate', output_dir, False)

    # Detect labels, scales and bars
    detect(make_path('Particulate'))

    # Crop located labels, scales and bars
    crop_scales(make_path('Particulate'), 'label_scale_bar_detector/localizer/darknet/result.json', output_dir)

    # These folders must exist even when no regions were detected.
    for folder_name in ("label", "scale", "bar"):
        create_dir(make_path(folder_name))

    # Read labels and scales
    labels_path = make_path("label")
    scales_path = make_path("scale")
    read_OCR_from_folder('label', labels_path, output_dir)
    read_OCR_from_folder('scale', scales_path, output_dir)
    drop_zeros(make_path("scales.csv"))

    # measure bar lengths and add to csv
    measure_bars(make_path("bar"), make_path("scales.csv"), scales_path)

    # Run particle segmentation
    run_segmentation(make_path("Particulate"), "particle_segmentation/Mask_RCNN", make_path("scales.csv"), output_dir)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run TEMExtraction on a research paper or a single image."
    )

    parser.add_argument(
        "--output_dir",
        required=True,
        help="Directory where analysis results will be stored."
    )

    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Enable GPU processing."
    )

    parser.add_argument(
        "--publisher",
        choices=["elsevier", "nature", "rsc", "springer"],
        help="Paper publisher."
    )

    parser.add_argument(
        "--html_source",
        help="Paper HTML URL or local HTML file."
    )

    parser.add_argument(
        "--input_image",
        default=None,
        help="Path to one image for manual-image analysis."
    )

    parser.add_argument(
        "--doi",
        default=None,
        help="DOI, required for Nature papers."
    )

    parser.add_argument(
        "--year",
        default=None,
        help="Publication year, required for Nature papers."
    )

    parser.add_argument(
        "--pdf_path",
        default=None,
        help="Article PDF path, required for Springer papers."
    )

    args = parser.parse_args()

    if args.input_image:
        if not os.path.isfile(args.input_image):
            parser.error("Input image does not exist: {}".format(args.input_image))
    else:
        if not args.publisher:
            parser.error("--publisher is required without --input_image.")
        if not args.html_source:
            parser.error("--html_source is required without --input_image.")

    run_pipeline_single(
        args.output_dir,
        args.gpu,
        args.publisher,
        args.html_source,
        args.doi,
        args.year,
        args.pdf_path,
        input_image=args.input_image
    )
