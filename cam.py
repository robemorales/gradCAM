import argparse
import os
import cv2
import numpy as np
import torch
import sys
sys.path.append('/home/rmorales/anaconda3/envs/myenv/MLAFM-master/')

import afm
import torch.nn as nn
from torchvision import models
from pytorch_grad_cam import (
    GradCAM, HiResCAM, ScoreCAM, GradCAMPlusPlus,
    AblationCAM, XGradCAM, EigenCAM, EigenGradCAM,
    LayerCAM, FullGrad, GradCAMElementWise
)
from pytorch_grad_cam import GuidedBackpropReLUModel
from pytorch_grad_cam.utils.image import (
    show_cam_on_image, deprocess_image, preprocess_image
)
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--use-cuda', action='store_true', default=False,
                        help='Use NVIDIA GPU acceleration')
    parser.add_argument('--network', default='resnet50', type=str,
                   choices=['resnet50', 'resnet101', 'resnet152'],
                   help='model architecture')

    parser.add_argument('--target', type=int, help='target category')
    parser.add_argument(
        '--image-path',
        type=str,
        default='./examples/both.png',
        help='Input image path')
    parser.add_argument('--aug-smooth', action='store_true',
                        help='Apply test time augmentation to smooth the CAM')
    parser.add_argument(
        '--eigen-smooth',
        action='store_true',
        help='Reduce noise by taking the first principle component'
        'of cam_weights*activations')
    parser.add_argument('--method', type=str, default='gradcam',
                        choices=[
                            'gradcam', 'hirescam', 'gradcam++',
                            'scorecam', 'xgradcam', 'ablationcam',
                            'eigencam', 'eigengradcam', 'layercam',
                            'fullgrad', 'gradcamelementwise'
                        ],
                        help='CAM method')

    parser.add_argument('--output-dir', type=str, default='output',
                        help='Output directory to save the images')
    args = parser.parse_args()
    args.use_cuda = args.use_cuda and torch.cuda.is_available()
    if args.use_cuda:
        print('Using GPU for acceleration')
    else:
        print('Using CPU for computation')

    return args


if __name__ == '__main__':
    """ python cam.py -image-path <path_to_image>
    Example usage of loading an image and computing:
        1. CAM
        2. Guided Back Propagation
        3. Combining both
    """

    args = get_args()
    methods = {
        "gradcam": GradCAM,
        "hirescam": HiResCAM,
        "scorecam": ScoreCAM,
        "gradcam++": GradCAMPlusPlus,
        "ablationcam": AblationCAM,
        "xgradcam": XGradCAM,
        "eigencam": EigenCAM,
        "eigengradcam": EigenGradCAM,
        "layercam": LayerCAM,
        "fullgrad": FullGrad,
        "gradcamelementwise": GradCAMElementWise
    }

    #model = models.resnet50(pretrained=True)
    #model = afm.__dict__[args.network](pretrained=True, num_classes=227)
    num_cls = 73
    model = models.resnet50(pretrained=True)
    model.fc = nn.Linear(model.fc.in_features, num_cls)
    model = torch.nn.DataParallel(model)
   #ckpt = torch.load('results/food_mlafm/model_best.pkl')
    ckpt = torch.load('/home/rmorales/anaconda3/envs/myenv/MLAFM-master/results/food/model_unimib2016.pkl')
    model.load_state_dict(ckpt)

    # Choose the target layer you want to compute the visualization for.
    # Usually this will be the last convolutional layer in the model.
    # Some common choices can be:
    # Resnet18 and 50: model.layer4
    # VGG, densenet161: model.features[-1]
    # mnasnet1_0: model.layers[-1]
    # You can print the model to help chose the layer
    # You can pass a list with several target layers,
    # in that case the CAMs will be computed per layer and then aggregated.
    # You can also try selecting all layers of a certain type, with e.g:
    # from pytorch_grad_cam.utils.find_layers import find_layer_types_recursive
    # find_layer_types_recursive(model, [torch.nn.ReLU])
    
    target_layers = [model.module.layer4[-1]]

    rgb_img = cv2.imread(args.image_path, flags=cv2.IMREAD_COLOR|cv2.IMREAD_IGNORE_ORIENTATION)[:, :, ::-1]
    rgb_img = np.float32(rgb_img) / 255
    input_tensor = preprocess_image(rgb_img,
                                    mean=[0.485, 0.456, 0.406],
                                    std=[0.229, 0.224, 0.225],
                                    size=224)
    print("este es el tensor: ",input_tensor)
    

    # Obtener la imagen inversa
    #inverse_img = 1.0 - rgb_img

    #input_tensor = preprocess_image(inverse_img, mean=[0.5, 0.5, 0.5],
    #                           std=[0.5, 0.5, 0.5])
    # We have to specify the target we want to generate
    # the Class Activation Maps for.
    # If targets is None, the highest scoring category (for every member in the batch) will be used.
    # You can target specific categories by
    # targets = [e.g ClassifierOutputTarget(285)/home/rmorales/anaconda3/envs/myenv/MLAFM-master/results/food#]
    targets = [ClassifierOutputTarget(args.target)] 

    # Using the with statement ensures the context is freed, and you can
    # recreate different CAM objects in a loop.
    cam_algorithm = methods[args.method]
    with cam_algorithm(model=model,
                       target_layers=target_layers,
                       use_cuda=args.use_cuda) as cam:


        # AblationCAM and ScoreCAM have batched implementations.
        # You can override the internal batch size for faster computation.
        cam.batch_size = 32
        grayscale_cam = cam(input_tensor=input_tensor,
                            targets=targets,
                            aug_smooth=args.aug_smooth,
                            eigen_smooth=args.eigen_smooth)

        grayscale_cam = grayscale_cam[0, :]

        #cam_image = show_cam_on_image(rgb_img, grayscale_cam, use_rgb=True)
        cam_image = show_cam_on_image(
            rgb_img, 
            cv2.resize(grayscale_cam, (rgb_img.shape[1], rgb_img.shape[0])), 
            use_rgb=True
        )

        cam_image = cv2.cvtColor(cam_image, cv2.COLOR_RGB2BGR)

    gb_model = GuidedBackpropReLUModel(model=model, use_cuda=args.use_cuda)
    gb = gb_model(input_tensor, target_category=None)

    cam_mask = cv2.merge([grayscale_cam, grayscale_cam, grayscale_cam])
    cam_gb = deprocess_image(cam_mask * gb)
    gb = deprocess_image(gb)

    os.makedirs(args.output_dir, exist_ok=True)

    cam_output_path = os.path.join(args.output_dir, f'{args.method}_cam.jpg')
    gb_output_path = os.path.join(args.output_dir, f'{args.method}_gb.jpg')
    cam_gb_output_path = os.path.join(args.output_dir, f'{args.method}_cam_gb.jpg')
    #Metrics
    
    #end-metrics
    cv2.imwrite(cam_output_path, cam_image)
    cv2.imwrite(gb_output_path, gb)
    cv2.imwrite(cam_gb_output_path, cam_gb)
# Now lets see how to evaluate this explanation:
from pytorch_grad_cam.metrics.cam_mult_image import CamMultImageConfidenceChange
from pytorch_grad_cam.utils.model_targets import ClassifierOutputSoftmaxTarget
from PIL import Image
# For the metrics we want to measure the change in the confidence, after softmax, that's why
# we use ClassifierOutputSoftmaxTarget.
targets = [ClassifierOutputSoftmaxTarget(args.target)]
cam_metric = CamMultImageConfidenceChange()
scores, visualizations = cam_metric(input_tensor, grayscale_cam, targets, model, return_visualization=True)
score = scores[0]
visualization = visualizations[0].cpu().numpy().transpose((1, 2, 0))
visualization = deprocess_image(visualization)
print(f"The confidence increase percent: {100*score}")
print("The visualization of the pertubated image for the metric:")
Image.fromarray(visualization)
