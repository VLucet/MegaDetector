########
#
# visualize_detector_output.py
#
# Render images with bounding boxes annotated on them to a folder, based on a
# detector output result file (json), optionally writing an HTML index file.
#
########

#%% Imports

import argparse
import json
import os
import random
import sys
from multiprocessing.pool import ThreadPool
from multiprocessing.pool import Pool
from typing import List
from functools import partial

from tqdm import tqdm

from data_management.annotations.annotation_constants import detector_bbox_category_id_to_name
from md_visualization import visualization_utils as vis_utils
from md_utils.ct_utils import get_max_conf
from md_utils import write_html_image_list
from detection.run_detector import get_typical_confidence_threshold_from_results


#%% Constants

# This will only be used if a category mapping is not available in the results file.
DEFAULT_DETECTOR_LABEL_MAP = {
    str(k): v for k, v in detector_bbox_category_id_to_name.items()
}


#%% Support functions

def render_image(entry,
                 detector_label_map,classification_label_map,
                 confidence_threshold,classification_confidence_threshold,
                 render_detections_only,preserve_path_structure,out_dir,images_dir,
                 output_image_width):
    
    rendering_result = {'failed_image':False,'missing_image':False,
                        'skipped_image':False,'annotated_image_path':None}
    
    image_id = entry['file']

    if 'failure' in entry and entry['failure'] is not None:
        rendering_result['failed_image'] = True
        return rendering_result

    assert 'detections' in entry and entry['detections'] is not None
    
    max_conf = get_max_conf(entry)
    if (max_conf < confidence_threshold) and render_detections_only:
        rendering_result['skipped_image'] = True
        return rendering_result
    
    image_obj = os.path.join(images_dir, image_id)
    if not os.path.exists(image_obj):
        print(f'Image {image_id} not found in images_dir')
        rendering_result['missing_image'] = True
        return rendering_result

    # If output_image_width is -1 or None, this will just return the original image
    image = vis_utils.resize_image(
        vis_utils.open_image(image_obj), output_image_width)

    vis_utils.render_detection_bounding_boxes(
        entry['detections'], image, 
        label_map=detector_label_map,
        classification_label_map=classification_label_map,
        confidence_threshold=confidence_threshold,
        classification_confidence_threshold=classification_confidence_threshold)

    if not preserve_path_structure:
        for char in ['/', '\\', ':']:
            image_id = image_id.replace(char, '~')
        annotated_img_path = os.path.join(out_dir, f'anno_{image_id}')
    else:
        assert not os.path.isabs(image_id), "Can't preserve paths when operating on absolute paths"
        annotated_img_path = os.path.join(out_dir, image_id)
        os.makedirs(os.path.dirname(annotated_img_path),exist_ok=True)
        
    image.save(annotated_img_path)
    rendering_result['annotated_image_path'] = annotated_img_path        

    return rendering_result


#%% Main function

def visualize_detector_output(detector_output_path: str,
                              out_dir: str,
                              images_dir: str,
                              confidence_threshold: float = 0.15,
                              sample: int = -1,
                              output_image_width: int = 700,
                              random_seed: int = None,
                              render_detections_only: bool = False,
                              classification_confidence_threshold = 0.1,
                              html_output_file = None,
                              html_output_options = None,
                              preserve_path_structure = False,
                              parallelize_rendering = False,
                              parallelize_rendering_n_cores = 10,
                              parallelize_rendering_with_threads = True) -> List[str]:
    
    """
    Draw bounding boxes on images given the output of a detector.

    Args:
        detector_output_path: str, path to detector output json file
        out_dir: str, path to directory for saving annotated images
        images_dir: str, path to images dir
        confidence: float, threshold above which annotations will be rendered
        sample: int, maximum number of images to annotate, -1 for all
        random_seed: seed for sampling (not relevant if sample == -1)
        output_image_width: int, width in pixels to resize images for display,
            set to -1 to use original image width
        random_seed: int, for deterministic image sampling when sample != -1
        render_detections_only: bool, only render images with above-threshold detections

    Returns: list of str, paths to annotated images
    """
    
    assert os.path.exists(detector_output_path), \
        'Detector output file does not exist at {}'.format(detector_output_path)

    assert os.path.isdir(images_dir), \
        'Image folder {} is not available'.format(images_dir)

    os.makedirs(out_dir, exist_ok=True)


    ##%% Load detector output

    with open(detector_output_path) as f:
        detector_output = json.load(f)
    assert 'images' in detector_output, (
        'Detector output file should be a json with an "images" field.')
    images = detector_output['images']
    
    if confidence_threshold is None:
        confidence_threshold = get_typical_confidence_threshold_from_results(detector_output)
        
    assert confidence_threshold >= 0 and confidence_threshold <= 1, (
        f'Confidence threshold {confidence_threshold} is invalid, must be in (0, 1).')
    
    if 'detection_categories' in detector_output:
        print('Using custom label mapping')
        detector_label_map = detector_output['detection_categories']
    else:
        detector_label_map = DEFAULT_DETECTOR_LABEL_MAP        

    num_images = len(images)
    print(f'Detector output file contains {num_images} entries.')

    if sample > 0:
        assert num_images >= sample, (
            f'Sample size {sample} greater than number of entries '
            f'({num_images}) in detector result.')

        if random_seed is not None:
            images = sorted(images, key=lambda x: x['file'])
            random.seed(random_seed)

        random.shuffle(images)
        images = sorted(images[:sample], key=lambda x: x['file'])
        print(f'Sampled {len(images)} entries from the detector output file.')


    ##%% Load images, annotate them and save

    print('Rendering detections above a confidence threshold of {}'.format(
        confidence_threshold))
    
    classification_label_map = None
    
    if 'classification_categories' in detector_output:
        classification_label_map = detector_output['classification_categories']
        
    rendering_results = []
    
    if parallelize_rendering:
        
        if parallelize_rendering_with_threads:
            worker_string = 'threads'
        else:
            worker_string = 'processes'
            
        if parallelize_rendering_n_cores is None:
            if parallelize_rendering_with_threads:
                pool = ThreadPool()
            else:
                pool = Pool()
        else:
            if parallelize_rendering_with_threads:
                pool = ThreadPool(parallelize_rendering_n_cores)
            else:
                pool = Pool(parallelize_rendering_n_cores)
            print('Rendering images with {} {}'.format(parallelize_rendering_n_cores,
                                                       worker_string))            
        rendering_results = list(tqdm(pool.imap(
                                 partial(render_image,detector_label_map=detector_label_map,
                                         classification_label_map=classification_label_map,
                                         confidence_threshold=confidence_threshold,
                                         classification_confidence_threshold=classification_confidence_threshold,
                                         render_detections_only=render_detections_only,
                                         preserve_path_structure=preserve_path_structure,
                                         out_dir=out_dir,
                                         images_dir=images_dir,
                                         output_image_width=output_image_width),
                                 images), total=len(images)))
        
    else:
                
        for entry in tqdm(images):
            
            rendering_result = render_image(entry,detector_label_map,classification_label_map,
                                            confidence_threshold,classification_confidence_threshold,
                                            render_detections_only,preserve_path_structure,out_dir,
                                            images_dir,output_image_width)
            rendering_results.append(rendering_result)
        
    # ...for each image
    
    failed_images = [r for r in rendering_results if r['failed_image']]
    missing_images = [r for r in rendering_results if r['missing_image']]
    skipped_images = [r for r in rendering_results if r['skipped_image']]
    
    print('Skipped {} failed images (of {})'.format(len(failed_images),len(images)))
    print('Skipped {} missing images (of {})'.format(len(missing_images),len(images)))
    print('Skipped {} below-threshold images (of {})'.format(len(skipped_images),len(images)))
    
    print(f'Rendered detection results to {out_dir}')

    annotated_image_paths = [r['annotated_image_path'] for r in rendering_results if \
                             r['annotated_image_path'] is not None]
    
    if html_output_file is not None:
        html_dir = os.path.dirname(html_output_file)
        annotated_image_paths_relative = [os.path.relpath(fn,html_dir) for fn in annotated_image_paths]
        _ = write_html_image_list.write_html_image_list(html_output_file,annotated_image_paths_relative,
                                                    options=html_output_options)
        
    return annotated_image_paths


#%% Command-line driver

def main() -> None:
    """Main function."""

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Annotate the bounding boxes predicted by a detector above '
                    'some confidence threshold, and save the annotated images.')
    parser.add_argument(
        'detector_output_path', type=str,
        help='Path to json output file of the detector')
    parser.add_argument(
        'out_dir', type=str,
        help='Path to directory where the annotated images will be saved. '
             'The directory will be created if it does not exist.')
    parser.add_argument(
        '-c', '--confidence', type=float, default=0.15,
        help='Value between 0 and 1, indicating the confidence threshold '
             'above which to visualize bounding boxes')
    parser.add_argument(
        '-i', '--images_dir', type=str, default=None,
        help='Path to a local directory where images are stored. This '
             'serves as the root directory for image paths in '
             'detector_output_path.')
    parser.add_argument(
        '-n', '--sample', type=int, default=-1,
        help='Number of images to be annotated and rendered. Set to -1 '
             '(default) to annotate all images in the detector output file. '
             'There may be fewer images if some are not found in images_dir.')
    parser.add_argument(
        '-w', '--output_image_width', type=int, default=700,
        help='Integer, desired width in pixels of the output annotated images. '
             'Use -1 to not resize. Default: 700.')
    parser.add_argument(
        '-r', '--random_seed', type=int, default=None,
        help='Integer, for deterministic order of image sampling')
    parser.add_argument(
        '-html', '--html_output_file', type=str, default=None,
        help='Filename to which we should write an HTML image index (off by default)')
    parser.add_argument(
        '--open_html_output_file', action='store_true',
        help='Open the .html output file when done')
    parser.add_argument(
        '-do', '--detections_only', action='store_true',
        help='Only render images with above-threshold detections (by default, '
             'both empty and non-empty images are rendered).')
    parser.add_argument(
        '-pps', '--preserve_path_structure', action='store_true',
        help='Preserve relative image paths (otherwise flattens and assigns unique file names)')

    if len(sys.argv[1:]) == 0:
        parser.print_help()
        parser.exit()

    args = parser.parse_args()
    visualize_detector_output(
        detector_output_path=args.detector_output_path,
        out_dir=args.out_dir,
        confidence_threshold=args.confidence,
        images_dir=args.images_dir,
        sample=args.sample,
        output_image_width=args.output_image_width,
        random_seed=args.random_seed,
        render_detections_only=args.detections_only,
        preserve_path_structure=args.preserve_path_structure,
        html_output_file=args.html_output_file)

    if args.html_output_file is not None and args.open_html_output_file:
        from md_utils.path_utils import open_file
        open_file(args.html_output_file)

if __name__ == '__main__':
    main()


#%% Interactive driver

if False:
    
    pass

    #%%
    
    detector_output_path = os.path.expanduser('~/postprocessing/bellevue-camera-traps/bellevue-camera-traps-2023-12-05-v5a.0.0/combined_api_outputs/bellevue-camera-traps-2023-12-05-v5a.0.0_detections.json')
    out_dir = r'g:\temp\preview'
    images_dir = r'g:\camera_traps\camera_trap_images'
    confidence_threshold = 0.15
    sample = 50
    output_image_width = 700
    random_seed = 1
    render_detections_only = True
    classification_confidence_threshold = 0.1
    html_output_file = os.path.join(out_dir,'index.html')
    html_output_options = None
    preserve_path_structure = False
    parallelize_rendering = True
    parallelize_rendering_n_cores = 10
    parallelize_rendering_with_threads = False

    _ = visualize_detector_output(detector_output_path,
                              out_dir,
                              images_dir,
                              confidence_threshold,
                              sample,
                              output_image_width,
                              random_seed,
                              render_detections_only,
                              classification_confidence_threshold,
                              html_output_file,
                              html_output_options,
                              preserve_path_structure,
                              parallelize_rendering,
                              parallelize_rendering_n_cores,
                              parallelize_rendering_with_threads)
    
    from md_utils.path_utils import open_file
    open_file(html_output_file)