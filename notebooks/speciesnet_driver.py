"""

speciesnet_driver.py
   
Semi-automated process for managing a local SpeciesNet job, including
standard postprocessing steps.  This version uses the complete ensemble logic
and therefore does not handle multi-species images.  If multi-species images
are rare in your data, consider using speciesnet_multispecies_driver.py instead.

"""

#%% Imports

import os
import json
import stat
import kagglehub

from megadetector.utils.path_utils import insert_before_extension
from megadetector.utils.wi_utils import generate_md_results_from_predictions_json
from megadetector.utils.wi_utils import generate_instances_json_from_folder
from megadetector.utils.ct_utils import split_list_into_fixed_size_chunks

import clipboard # noqa


#%% Constants I set for each job

organization_name = 'wildlab'
job_name = 'all_crop'

input_folder = '/media/vlucet/T7ShieldSSD/trailcam/cropped'
assert not input_folder.endswith('/')
model_file = kagglehub.model_download("google/speciesnet/keras/v4.0.0a")

country_code = "CAN"
state_code = None

base_folder = "~/Documents/wildlab/camtrap-rof"

speciesnet_folder = os.path.expanduser(f'{base_folder}/repos/cameratrapai')
speciesnet_pt_environment_name = 'speciesnet'
speciesnet_tf_environment_name = 'speciesnet-tf'

# Can be None to omit the CUDA prefix
gpu_number = 0

# Possibly split into multiple batches; you'll run most of this notebook
# separately on each batch.
n_batches = 1

# This is not related to running the model, only to postprocessing steps
# in this notebook.  Threads work better on Windows, processes on Linux.
use_threads_for_parallelization = (os.name == 'nt')
max_images_per_chunk = 2000
classifier_batch_size = 16

# Only necessary when using a custom taxonomy list
custom_taxa_list = None
taxonomy_file = os.path.join(model_file,'taxonomy_release.txt')

# Use this when instances.json has already been generated
force_instances_json = None


#%% Validate constants, prepare folders and dependent constants

if gpu_number is not None:
    cuda_prefix = 'export CUDA_VISIBLE_DEVICES={} && '.format(gpu_number)
else:
    cuda_prefix = ''

# assert organization_name != 'organization_name'
# assert job_name != 'job_name'
assert country_code != None

output_base = os.path.expanduser(f"{base_folder}/data/json/speciesnet/postprocessing/")
os.makedirs(output_base,exist_ok=True)
preview_folder_base = os.path.join(output_base,'preview')
instances_json = os.path.join(output_base,'instances.json')

assert os.path.isdir(speciesnet_folder)
assert os.path.isdir(input_folder)

detector_output_file_modular = \
    os.path.join(output_base,job_name + '-detector_output_modular.json')
classifier_output_file_modular = \
    os.path.join(output_base,job_name + '-classifier_output_modular.json')
ensemble_output_file_modular = \
    os.path.join(output_base,job_name + '-ensemble_output_modular.json')

for fn in [detector_output_file_modular,classifier_output_file_modular,ensemble_output_file_modular]:
    if os.path.exists(fn):
        print('** Warning, file {} exists, this is OK if you are resuming **\n'.format(fn))

if custom_taxa_list is not None:
    assert os.path.isfile(custom_taxa_list)
    assert os.path.isfile(taxonomy_file)


#%% Generate or load instances.json

if force_instances_json is None:
    
    instances = generate_instances_json_from_folder(folder=input_folder,
                                                    country=country_code,
                                                    admin1_region=state_code,
                                                    output_file=instances_json,
                                                    filename_replacements=None)
    
    print('Generated {} instances'.format(len(instances['instances'])))    
    del instances
    
else:
    
    with open(force_instances_json, 'r') as f:
        instances = json.load(f)
    print('Loaded {} instances from {}'.format(
        len(instances['instances']),force_instances_json))
    instances_json = force_instances_json
    del instances


#%% Possibly split here into multiple batches

from megadetector.utils.wi_utils import split_instances_into_n_batches

if n_batches > 1:
    
    output_files = split_instances_into_n_batches(instances_json, n_batches, output_files=None)
        

#%% Run detector

detector_commands = []
detector_commands.append(f'{cuda_prefix} cd {speciesnet_folder} && mamba activate {speciesnet_pt_environment_name}')

cmd = 'python speciesnet/scripts/run_model.py --detector_only --model "{}"'.format(model_file)
cmd += ' --instances_json "{}"'.format(instances_json)
cmd += ' --predictions_json "{}"'.format(detector_output_file_modular)
detector_commands.append(cmd)

detector_cmd = '\n\n'.join(detector_commands)
print(detector_cmd); clipboard.copy(detector_cmd)


#%% Validate detector results

from megadetector.utils.wi_utils import validate_predictions_file
_ = validate_predictions_file(detector_output_file_modular,instances_json)

#%% Prep classifier
   
chunk_folder = os.path.join(output_base,'chunks')
os.makedirs(chunk_folder,exist_ok=True)

print('Reading instances json...')

with open(instances_json,'r') as f:
    instances_dict = json.load(f)

instances = instances_dict['instances']
       
chunks = split_list_into_fixed_size_chunks(instances,max_images_per_chunk)
print('Split {} instances into {} chunks'.format(len(instances),len(chunks)))

chunk_scripts = []

print('Reading detection results...')

# with open(detector_output_file_modular,'r') as f:
#     detections = json.load(f)

# detection_filepath_to_instance = {p['filepath']:p for p in detections['predictions']}

#%% Run classifier

chunk_prediction_files = []

# i_chunk = 0; chunk = chunks[i_chunk]
for i_chunk,chunk in enumerate(chunks):
    
    chunk_str = str(i_chunk).zfill(3)
    
    chunk_instances_json = os.path.join(chunk_folder,'instances_chunk_{}.json'.format(
        chunk_str))
    chunk_instances_dict = {'instances':chunk}
    with open(chunk_instances_json,'w') as f:
        json.dump(chunk_instances_dict,f,indent=1)
    
    # chunk_detections_json = os.path.join(chunk_folder,'detections_chunk_{}.json'.format(
    #     chunk_str))
    # detection_predictions_this_chunk = []
    
    images_this_chunk = [instance['filepath'] for instance in chunk]
    
    # for image_fn in images_this_chunk:
    #     assert image_fn in detection_filepath_to_instance
    #     detection_predictions_this_chunk.append(detection_filepath_to_instance[image_fn])
        
    # detection_predictions_dict = {'predictions':detection_predictions_this_chunk}
    
    # with open(chunk_detections_json,'w') as f:
    #     json.dump(detection_predictions_dict,f,indent=1)
                
    chunk_predictions_json = os.path.join(chunk_folder,'predictions_chunk_{}.json'.format(
        chunk_str))
    
    if os.path.isfile(chunk_predictions_json):
        print('Warning: chunk output file {} exists'.format(chunk_predictions_json))
        
    chunk_prediction_files.append(chunk_predictions_json)
    
    chunk_script = os.path.join(chunk_folder,'run_chunk_{}.sh'.format(i_chunk))
    cmd = 'python -m speciesnet.scripts.run_model --classifier_only --model "{}"'.format(
        model_file)
    cmd += ' --instances_json "{}"'.format(chunk_instances_json)
    cmd += ' --predictions_json "{}"'.format(chunk_predictions_json)
    # cmd += ' --detections_json "{}"'.format(chunk_detections_json)
    cmd += ' --bypass_prompts'
    cmd += ' --geofence'
    if country_code is not None:
       cmd += ' --country {}'.format(country_code)
    if classifier_batch_size is not None:
       cmd += ' --batch_size {}'.format(classifier_batch_size)
       
    chunk_script_file = os.path.join(chunk_folder,'run_chunk_{}.sh'.format(chunk_str))
    with open(chunk_script_file,'w') as f:
        f.write(cmd)
    st = os.stat(chunk_script_file)
    os.chmod(chunk_script_file, st.st_mode | stat.S_IEXEC)
    
    chunk_scripts.append(chunk_script_file)
    
# ...for each chunk

classifier_script_file = os.path.join(output_base,'run_all_classifier_chunks.sh')            
   
classifier_init_cmd = f'{cuda_prefix} cd {speciesnet_folder} && mamba activate {speciesnet_tf_environment_name}'
with open(classifier_script_file,'w') as f:
    f.write('set -e\n')
    # f.write(classifier_init_cmd + '\n')
    for s in chunk_scripts:
        f.write(s + '\n')

st = os.stat(classifier_script_file)
os.chmod(classifier_script_file, st.st_mode | stat.S_IEXEC)
   
classifier_cmd = '\n\n'.join([classifier_init_cmd,classifier_script_file])
print(classifier_cmd); clipboard.copy(classifier_cmd)
    

#%% ############################################################################
#%% Merge classification results batches

from megadetector.utils.wi_utils import merge_prediction_json_files

merge_prediction_json_files(input_prediction_files=chunk_prediction_files,
                            output_prediction_file=classifier_output_file_modular)
    

#%% Validate classification results

from megadetector.utils.wi_utils import validate_predictions_file
_ = validate_predictions_file(classifier_output_file_modular,instances_json)


#%% Run ensemble

# It doesn't matter here which environment we use
ensemble_commands = []
ensemble_commands.append(f'{cuda_prefix} cd {speciesnet_folder} && mamba activate {speciesnet_pt_environment_name}')

cmd = 'python speciesnet/scripts/run_model.py --ensemble_only --model "{}"'.format(model_file)
cmd += ' --instances_json "{}"'.format(instances_json)
cmd += ' --predictions_json "{}"'.format(ensemble_output_file_modular)
cmd += ' --detections_json "{}"'.format(detector_output_file_modular)
cmd += ' --classifications_json "{}"'.format(classifier_output_file_modular)

if custom_taxa_list is not None:
    cmd += ' --nogeofence'
ensemble_commands.append(cmd)

ensemble_cmd = '\n\n'.join(ensemble_commands)
# print(ensemble_cmd); clipboard.copy(ensemble_cmd)


#%% Validate ensemble results

from megadetector.utils.wi_utils import validate_predictions_file
_ = validate_predictions_file(ensemble_output_file_modular,instances_json)


#%% Generate a list of corrections made by geofencing, and counts

from megadetector.utils.wi_utils import find_geofence_adjustments
from megadetector.utils.ct_utils import is_list_sorted

rollup_pair_to_count = find_geofence_adjustments(ensemble_output_file_modular,
                                                 use_latin_names = False)

min_count = 10

geofence_footer = ''

rollup_pair_to_count = \
    {key: value for key, value in rollup_pair_to_count.items() if value >= min_count}

# rollup_pair_to_count is sorted in descending order by count
assert is_list_sorted(list(rollup_pair_to_count.values()),reverse=True)

if custom_taxa_list is not None:
    assert len(rollup_pair_to_count) == 0, \
        'Geofencing should have been disabled when running with a custom taxa list'
        
if len(rollup_pair_to_count) > 0:
    
    geofence_footer = \
        '<h3>Geofence changes that occurred more than {} times</h3>\n'.format(min_count)
    geofence_footer += '<div class="contentdiv">\n'
    
    print('\nRollup changes with count > {}:'.format(min_count))
    for rollup_pair in rollup_pair_to_count.keys():
        count = rollup_pair_to_count[rollup_pair]
        rollup_pair_s = rollup_pair.replace(',',' --> ')
        print('{}: {}'.format(rollup_pair_s,count))
        rollup_pair_html = rollup_pair.replace(',',' &rarr; ')
        geofence_footer += '{} ({})<br/>\n'.format(rollup_pair_html,count)

    geofence_footer += '</div>\n'

else:
    
    print('\nNo corrections made by geofencing')
    

#%% Convert output file to MD format 

assert os.path.isfile(ensemble_output_file_modular)
ensemble_output_file_md_format = insert_before_extension(ensemble_output_file_modular,
                                                         'md-format')

generate_md_results_from_predictions_json(predictions_json_file=ensemble_output_file_modular,
                                          md_results_file=ensemble_output_file_md_format,
                                          base_folder=input_folder+'/')

# from megadetector.utils.path_utils import open_file; open_file(ensemble_output_file_md_format)


#%% Confirm that all the right files are in the results

import json
from megadetector.utils.path_utils import find_images

with open(ensemble_output_file_md_format,'r') as f:
    d = json.load(f)

filenames_in_results = set([im['file'] for im in d['images']])
images_in_folder = find_images(input_folder,recursive=True,return_relative_paths=True)
images_in_folder = [fn for fn in images_in_folder if not fn.startswith('$RECYCLE')]
images_in_folder = set(images_in_folder)

for fn in filenames_in_results:
    assert fn in images_in_folder, \
        'Image {} present in results but not in folder'.format(fn)

for fn in images_in_folder:
    assert fn in filenames_in_results, \
        'Image {} present in folder but not in results'.format(fn)
        
n_failures = 0
        
# im = d['images'][0]
for im in d['images']:
    if 'failure' in im:
        n_failures += 1
        
print('Loaded results for {} images with {} failures'.format(
    len(images_in_folder),n_failures))


#%% Possibly apply a custom species list

from megadetector.utils.wi_utils import restrict_to_taxa_list

if custom_taxa_list is not None:
    
    taxa_list = custom_taxa_list
    speciesnet_taxonomy_file = taxonomy_file
    input_file = ensemble_output_file_md_format
    output_file = insert_before_extension(ensemble_output_file_md_format,'custom-species')
    allow_walk_down = False
    
    restrict_to_taxa_list(taxa_list=taxa_list,
                          speciesnet_taxonomy_file=speciesnet_taxonomy_file,
                          input_file=input_file,
                          output_file=output_file,
                          allow_walk_down=allow_walk_down)
    
    ensemble_output_file_md_format = output_file
    
    
#%% Generate a list of all predictions made, with counts

from megadetector.utils.ct_utils import sort_dictionary_by_value

with open(ensemble_output_file_md_format,'r') as f:
    d = json.load(f)

classification_category_to_count = {}

# im = d['images'][0]
for im in d['images']:
    if 'detections' in im and im['detections'] is not None:
        for det in im['detections']:
            if 'classifications' in det:
                class_id = det['classifications'][0][0]
                if class_id not in classification_category_to_count:
                    classification_category_to_count[class_id] = 0
                else:
                    classification_category_to_count[class_id] = \
                        classification_category_to_count[class_id] + 1

category_name_to_count = {}

for class_id in classification_category_to_count:
    category_name = d['classification_categories'][class_id]
    category_name_to_count[category_name] = \
        classification_category_to_count[class_id]

category_name_to_count = sort_dictionary_by_value(
    category_name_to_count,reverse=True)

category_count_footer = ''
category_count_footer += '<br/>\n'
category_count_footer += \
    '<h3>Category counts (for the whole dataset, not just the sample used for this page)</h3>\n'
category_count_footer += '<div class="contentdiv">\n'

for category_name in category_name_to_count.keys():
    count = category_name_to_count[category_name]
    category_count_html = '{}: {}<br>\n'.format(category_name,count)    
    category_count_footer += category_count_html

category_count_footer += '</div>\n'


#%% Optional RDE prep: define custom camera folder function

if False:
    
    #%% Sample custom camera folder function
    
    def custom_relative_path_to_location(relative_path):
        
        relative_path = relative_path.replace('\\','/')    
        tokens = relative_path.split('/')        
        location_name = '/'.join(tokens[0:2])
        return location_name
    
    #%% Test custom function
    
    from tqdm import tqdm
    
    with open(ensemble_output_file_md_format,'r') as f:
        d = json.load(f)
    image_filenames = [im['file'] for im in d['images']]

    location_names = set()

    # relative_path = image_filenames[0]
    for relative_path in tqdm(image_filenames):
        
        location_name = custom_relative_path_to_location(relative_path)
        # location_name = image_file_to_camera_folder(relative_path)
        
        location_names.add(location_name)
        
    location_names = list(location_names)
    location_names.sort()

    for s in location_names:
        print(s)


#%% Repeat detection elimination, phase 1

from megadetector.postprocessing.repeat_detection_elimination import repeat_detections_core
from megadetector.utils.ct_utils import image_file_to_camera_folder

rde_base = os.path.join(output_base,'rde')
options = repeat_detections_core.RepeatDetectionOptions()

options.confidenceMin = 0.1
options.confidenceMax = 1.01
options.iouThreshold = 0.85
options.occurrenceThreshold = 15
options.maxSuspiciousDetectionSize = 0.2
# options.minSuspiciousDetectionSize = 0.05

options.parallelizationUsesThreads = use_threads_for_parallelization
options.nWorkers = 10

# This will cause a very light gray box to get drawn around all the detections
# we're *not* considering as suspicious.
options.bRenderOtherDetections = True
options.otherDetectionsThreshold = options.confidenceMin

options.bRenderDetectionTiles = True
options.maxOutputImageWidth = 2000
options.detectionTilesMaxCrops = 100

# options.lineThickness = 5
# options.boxExpansion = 8

options.customDirNameFunction = image_file_to_camera_folder
# options.customDirNameFunction = custom_relative_path_to_location

options.bRenderHtml = False
options.imageBase = input_folder
rde_string = 'rde_{:.3f}_{:.3f}_{}_{:.3f}'.format(
    options.confidenceMin, options.iouThreshold,
    options.occurrenceThreshold, options.maxSuspiciousDetectionSize)
options.outputBase = os.path.join(rde_base, rde_string)
options.filenameReplacements = None # {'':''}

# Exclude people and vehicles from RDE
# options.excludeClasses = [2,3]

# options.maxImagesPerFolder = 50000
# options.includeFolders = ['a/b/c','d/e/f']
# options.excludeFolders = ['a/b/c','d/e/f']

options.debugMaxDir = -1
options.debugMaxRenderDir = -1
options.debugMaxRenderDetection = -1
options.debugMaxRenderInstance = -1

# Can be None, 'xsort', or 'clustersort'
options.smartSort = 'xsort'

suspicious_detection_results = \
    repeat_detections_core.find_repeat_detections(ensemble_output_file_md_format,
                                                  outputFilename=None,
                                                  options=options)


#%% Manual RDE step

from megadetector.utils.path_utils import open_file

## DELETE THE VALID DETECTIONS ##

# If you run this line, it will open the folder up in your file browser
open_file(os.path.dirname(suspicious_detection_results.filterFile),
          attempt_to_open_in_wsl_host=True)


#%% Re-filtering

from megadetector.postprocessing.repeat_detection_elimination import \
    remove_repeat_detections

filtered_output_filename = insert_before_extension(ensemble_output_file_md_format, 
                                                              'filtered_{}'.format(rde_string))

remove_repeat_detections.remove_repeat_detections(
    inputFile=ensemble_output_file_md_format,
    outputFile=filtered_output_filename,
    filteringDir=os.path.dirname(suspicious_detection_results.filterFile)
    )


#%% Preview

from megadetector.utils.path_utils import open_file
from megadetector.postprocessing.postprocess_batch_results import \
    PostProcessingOptions, process_batch_results

assert os.path.isfile(ensemble_output_file_md_format)

try:
    preview_file = filtered_output_filename
    print('Using RDE results for preview')
except:
    preview_file = ensemble_output_file_md_format
    print('RDE results not found, using raw results for preview')

preview_folder = preview_folder_base

render_animals_only = False

footer_text = geofence_footer + category_count_footer

options = PostProcessingOptions()
options.image_base_dir = input_folder
options.include_almost_detections = True
options.num_images_to_sample = 10000
options.confidence_threshold = 0.2
options.almost_detection_confidence_threshold = options.confidence_threshold - 0.05
options.ground_truth_json_file = None
options.separate_detections_by_category = True
options.sample_seed = 0
options.max_figures_per_html_file = 2500
options.sort_classification_results_by_count = True
options.footer_text = footer_text

options.parallelize_rendering = True
options.parallelize_rendering_n_cores = 10
options.parallelize_rendering_with_threads = use_threads_for_parallelization

if render_animals_only:
    options.rendering_bypass_sets = ['detections_person','detections_vehicle',
                                     'detections_person_vehicle','non_detections']

preview_output_base = os.path.join(preview_folder,
    job_name + '_{:.3f}'.format(options.confidence_threshold))
if render_animals_only:
    preview_output_base = preview_output_base + '_animals_only'

os.makedirs(preview_output_base, exist_ok=True)
print('Processing to {}'.format(preview_output_base))

options.md_results_file = preview_file
options.output_dir = preview_output_base
ppresults = process_batch_results(options)
html_output_file = ppresults.output_html_file
open_file(html_output_file,attempt_to_open_in_wsl_host=True,browser_name='chrome')
# import clipboard; clipboard.copy(html_output_file)


#%% Zip results files

from megadetector.utils.path_utils import parallel_zip_files

json_files = os.listdir(output_base)
json_files = [fn for fn in json_files if fn.endswith('.json')]
json_files = [os.path.join(output_base,fn) for fn in json_files]

parallel_zip_files(json_files,verbose=True)


#%% Scrap

# if False:
    
#     pass

#     #%% Run everything using SpeciesNet (all-in-one)
    
#     ensemble_commands = []
#     ensemble_commands.append(f'cd {speciesnet_folder} && mamba activate {speciesnet_pt_environment_name}')
    
#     if instances_json is not None:
#         source_specifier = '--instances_json "{}"'.format(instances_json)
#     else:
#         source_specifier = '--folders "{}"'.format(input_folder)
        
#     ensemble_output_file_all_in_one = os.path.join(output_base,job_name + '-ensemble_output_all_in_one.json')
        
#     cmd = '{} python scripts/run_model.py --model "{}"'.format(cuda_prefix,model_file)
#     cmd += ' ' + source_specifier
#     cmd += ' --predictions_json "{}"'.format(ensemble_output_file_all_in_one)
#     ensemble_commands.append(cmd)
    
#     ensemble_cmd = '\n\n'.join(ensemble_commands)
#     print(ensemble_cmd)
#     # clipboard.copy(ensemble_cmd)
    

#     #%% Run everything using MD + SpeciesNet
    
#     md_environment_name = 'megadetector'
#     md_folder = os.path.expanduser('~/git/MegaDetector/megadetector')
#     md_python_path = '{}:{}'.format(
#         os.path.expanduser('~/git/yolov5-md'),
#         os.path.expanduser('~/git/MegaDetector'))

#     detector_output_file_md = os.path.join(output_base,job_name + '-detector_output_md.json')
#     detector_output_file_predictions_format_md = insert_before_extension(detector_output_file_md,'predictons-format')
#     classifier_output_file_md = os.path.join(output_base,job_name + '-classifier_output_md.json')
#     ensemble_output_file_md = os.path.join(output_base,job_name + '-ensemble_output_md.json')
    
#     if instances_json is not None:
#         source_specifier = '--instances_json "{}"'.format(instances_json)
#     else:
#         source_specifier = '--folders "{}"'.format(input_folder)
    
#     ## Run MegaDetector
    
#     megadetector_commands = []
#     megadetector_commands.append(f'export PYTHONPATH={md_python_path}')
#     megadetector_commands.append(f'cd {md_folder}')
#     megadetector_commands.append(f'mamba activate {md_environment_name}')
#     cmd = '{} python detection/run_detector_batch.py MDV5A "{}" "{}" --quiet --recursive'.format(
#         cuda_prefix, input_folder, detector_output_file_md)
#     # Use absolute paths
#     # cmd += ' --output_relative_filenames'
#     megadetector_commands.append(cmd)
    
#     megadetector_cmd = '\n\n'.join(megadetector_commands)
#     # print(megadetector_cmd); clipboard.copy(megadetector_cmd)
    
#     ## Convert to predictions format
    
#     conversion_commands = ['']
#     conversion_commands.append(f'cd {md_folder}')
#     conversion_commands.append(f'mamba activate {md_environment_name}')
    
#     cmd = 'python postprocessing/md_to_wi.py "{}" "{}"'.format(
#             detector_output_file_md,detector_output_file_predictions_format_md)
#     conversion_commands.append(cmd)
    
#     conversion_cmd = '\n\n'.join(conversion_commands)
#     # print(conversion_cmd); clipboard.copy(conversion_cmd)
    
#     ## Run classifier
    
#     classifier_commands = ['']
#     classifier_commands.append(f'cd {speciesnet_folder} && mamba activate {speciesnet_tf_environment_name}')
    
#     cmd = '{} python scripts/run_model.py --classifier_only --model "{}"'.format(
#         cuda_prefix,model_file)
#     cmd += ' ' + source_specifier
#     cmd += ' --predictions_json "{}"'.format(classifier_output_file_md)
#     cmd += ' --detections_json "{}"'.format(detector_output_file_predictions_format_md)
#     classifier_commands.append(cmd)
    
#     classifier_cmd = '\n\n'.join(classifier_commands)
#     # print(classifier_cmd); clipboard.copy(classifier_cmd)
    
#     ## Run ensemble
    
#     # It doesn't matter here which environment we use
#     ensemble_commands = ['']
#     ensemble_commands.append(f'cd {speciesnet_folder} && mamba activate {speciesnet_tf_environment_name}')
    
#     cmd = '{} python scripts/run_model.py --ensemble_only --model "{}"'.format(
#         cuda_prefix,model_file)
#     cmd += ' ' + source_specifier
#     cmd += ' --predictions_json "{}"'.format(ensemble_output_file_md)
#     cmd += ' --detections_json "{}"'.format(detector_output_file_predictions_format_md)
#     cmd += ' --classifications_json "{}"'.format(classifier_output_file_md)
#     ensemble_commands.append(cmd)
    
#     ensemble_cmd = '\n\n'.join(ensemble_commands)
#     # print(ensemble_cmd); clipboard.copy(ensemble_cmd)
    
#     ## All in one long command
    
#     modular_command = '\n\n'.join([megadetector_cmd,conversion_cmd,classifier_cmd,ensemble_cmd])
#     print(modular_command)
#     # clipboard.copy(modular_command)


#     #%% Run the classifier in a single command
    
#     if max_images_per_chunk is None:
       
#         classifier_commands = []
#         classifier_commands.append(f'{cuda_prefix} cd {speciesnet_folder} && mamba activate {speciesnet_tf_environment_name}')
        
#         cmd = 'python scripts/run_model.py --classifier_only --model "{}"'.format(model_file)
#         cmd += ' ' + source_specifier
#         cmd += ' --predictions_json "{}"'.format(classifier_output_file_modular)
#         cmd += ' --detections_json "{}"'.format(detector_output_file_modular)
#         if classifier_batch_size is not None:
#            cmd += ' --batch_size {}'.format(classifier_batch_size)
#         classifier_commands.append(cmd)
       
#         classifier_cmd = '\n\n'.join(classifier_commands)
#         # print(classifier_cmd); clipboard.copy(classifier_cmd)
       
