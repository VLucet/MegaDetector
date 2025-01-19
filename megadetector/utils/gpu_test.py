"""

gpu_test.py

Simple script to verify CUDA availability, used to verify a CUDA environment
for TF or PyTorch

"""

#%% Torch/TF test functions

def torch_test():
    """
    Print diagnostic information about Torch/CUDA status, including Torch/CUDA versions
    and all available CUDA device names.
    
    Returns:
        int: The number of CUDA devices reported by PyTorch.
    """
    
    try:
        import torch
    except Exception as e: #noqa
        print('PyTorch unavailable, not running PyTorch tests.  PyTorch import error was:\n{}'.format(
            str(e)))
        return

    print('Torch version: {}'.format(str(torch.__version__)))
    print('CUDA available (according to PyTorch): {}'.format(torch.cuda.is_available()))
    print('CUDA version (according to PyTorch): {}'.format(torch.version.cuda))
    print('CuDNN version (according to PyTorch): {}'.format(torch.backends.cudnn.version()))

    device_ids = list(range(torch.cuda.device_count()))
    
    if len(device_ids) > 0:        
        cuda_str = 'Found {} CUDA devices:'.format(len(device_ids))
        print(cuda_str)
        
        for device_id in device_ids:
            device_name = 'unknown'
            try:
                device_name = torch.cuda.get_device_name(device=device_id)
            except Exception as e: #noqa
                pass
            print('{}: {}'.format(device_id,device_name))
    else:
        print('No GPUs reported by PyTorch')
        
    return len(device_ids)


def tf_test():
    """
    Print diagnostic information about TF/CUDA status.
    
    Returns:
        int: The number of CUDA devices reported by PyTorch.    
    """
    
    try:
        import tensorflow as tf
    except Exception as e: #noqa
        print('TensorFlow unavailable, not running TF tests.  TF import error was:\n{}'.format(
            str(e)))
        return
    
    gpus = tf.config.list_physical_devices('GPU')
    if gpus is None:
        gpus = []
        
    if len(gpus) > 0:
        print('TensorFlow found the following GPUs:')
        for gpu in gpus:
            print(gpu.name)
            
        from tensorflow.python.platform import build_info as build
        print(f"TF version: {tf.__version__}")
        print(f"CUDA version reported by TensorFlow: {build.build_info['cuda_version']}")
        print(f"CuDNN version reported by TensorFlow: {build.build_info['cudnn_version']}")
    else:
        print('No GPUs reported by TensorFlow')
        
    return len(gpus)
 

#%% Command-line driver
    
if __name__ == '__main__':    
    
    print('*** Running Torch tests ***\n')
    torch_test()
    
    print('\n*** Running TF tests ***\n')
    tf_test()
