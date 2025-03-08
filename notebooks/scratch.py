with open(classifier_output_file_modular,'r') as f:
        d = json.load(f)
predictions_dat = d['predictions']
with open(instances_json,'r') as f:
    ins = json.load(f)
instances_dat = ins['instances']

set1=(set([x['filepath'] for x in predictions_dat]))
set2=(set([x['filepath'] for x in instances_dat]))
differences = list(set1.symmetric_difference(set2))