'''
evaluation
'''
import argparse
import os
import random
import time
from tqdm import tqdm
import open3d as o3d
import numpy as np
import importlib

import torch
import torch.nn as nn
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim as optim
import torch.optim.lr_scheduler as lr_scheduler
import torch.utils.data
import torch.nn.functional as F
from torch.autograd import Variable

parser = argparse.ArgumentParser()
parser.add_argument('--batchSize', type=int, default=32, help='input batch size')
parser.add_argument('--workers', type=int, default=8, help='number of data loading workers')
parser.add_argument('--nepoch', type=int, default=60, help='number of epochs to train for')
parser.add_argument('--ngpu', type=int, default=1, help='# GPUs')
parser.add_argument('--main_gpu', type=int, default=0, help='main GPU id') # CUDA_VISIBLE_DEVICES=0 python eval.py

parser.add_argument('--size', type=str, default='full', help='how many samples do we load: small | full')
parser.add_argument('--bit_width', type=int, default=4, help='quantize for bit width')
parser.add_argument('--SAMPLE_NUM', type=int, default = 1024,  help='number of sample points')
parser.add_argument('--JOINT_NUM', type=int, default = 21,  help='number of joints')
parser.add_argument('--INPUT_FEATURE_NUM', type=int, default = 3,  help='number of input point features')
parser.add_argument('--stacks', type=int, default = 3, help='start epoch')

parser.add_argument('--save_root_dir', type=str, default='./results',  help='output folder')
parser.add_argument('--model', type=str, default = 'best_model.pth',  help='model name for training resume')
parser.add_argument('--test_path', type=str, default = '../dataset',  help='model name for training resume')
parser.add_argument('--protocal', type=str, default = 's0',  help='model name for training resume')

parser.add_argument('--dataset', type=str, default = 'dexycb', help='optimizer name for training resume')
parser.add_argument('--model_name', type=str, default = 'handdagt',  help='')
parser.add_argument('--gpu', type=str, default = '3',  help='gpu')

opt = parser.parse_args()
# print (opt)

module = importlib.import_module('network_'+opt.model_name)

os.environ["CUDA_VISIBLE_DEVICES"]=opt.gpu

opt.manualSeed = 1
random.seed(opt.manualSeed)
torch.manual_seed(opt.manualSeed)


if opt.dataset == 'dexycb':
	save_dir = os.path.join(opt.save_root_dir, opt.dataset+ '_'+opt.protocal +'_' + opt.model_name+'_'+str(opt.stacks)+'stacks')
	from dataloader import loader 
	opt.JOINT_NUM = 21
elif opt.dataset == 'nyu':
	# save_dir = os.path.join(opt.save_root_dir, opt.dataset+ '_' + opt.model_name+'_'+ str(opt.stacks)+'stacks')
	save_dir = os.path.join(opt.save_root_dir, opt.dataset+ '_' + opt.model_name+'_'+ str(opt.stacks)+'stacks')
	from dataloader import loader
	opt.JOINT_NUM = 14


# 1. Load data                                         
if opt.dataset == 'dexycb' :
	test_data = loader.DexYCBDataset(opt.protocal, 'test', opt.test_path)
elif opt.dataset == 'nyu':
	test_data = loader.nyu_loader(opt.test_path, 'test', joint_num=opt.JOINT_NUM)
test_dataloader = torch.utils.data.DataLoader(test_data, batch_size=opt.batchSize,
                                          shuffle=False, num_workers=int(opt.workers), pin_memory=False)
                                          
print('#Test data:', len(test_data))
print (opt)



# 2. Define model, loss
model = getattr(module, 'HandModel')(joints=opt.JOINT_NUM, stacks=opt.stacks)

if opt.ngpu > 1:
    model.netR_1 = torch.nn.DataParallel(model.netR_1, range(opt.ngpu))
    model.netR_2 = torch.nn.DataParallel(model.netR_2, range(opt.ngpu))
    model.netR_3 = torch.nn.DataParallel(model.netR_3, range(opt.ngpu))
if opt.model != '':

	model.load_state_dict(torch.load(os.path.join(opt.save_root_dir, opt.model)), strict=False)
		
model.cuda()
# print(model)

parameters = model.parameters()
total_params = sum(p.numel() for p in model.parameters() if p.requires_grad) #add
print(f"Total number of parameters: {total_params}")


criterion = nn.MSELoss(size_average=True).cuda()

# # 3. evaluation
# torch.cuda.synchronize()
#
# model.eval()
# test_mse = 0.0
# test_wld_err = 0.0
# test_wld_err_mean = 0.0
#
# timer = 0
# total_samples = 0
#
# saved_points = []
# saved_gt = []
# saved_fold1 = []
# saved_final = []
# saved_error = []
# saved_length = []
#
# for i, data in enumerate(tqdm(test_dataloader, 0)):
#
# 	torch.cuda.synchronize()
# 	with torch.no_grad():
# 		# 3.2.1 load inputs and targets
# 		if opt.dataset == "nyu":
# 			img, points, gt_xyz, uvd_gt, center, M, cube, cam_para, volume_length = data
# 			volume_length = volume_length.cuda()
# 		else:
# 			img, points, gt_xyz, uvd_gt, center, M, cube, cam_para = data
# 			volume_length = 250.
#
# 		points, gt_xyz, img = points.cuda(),  gt_xyz.cuda(), img.cuda()
# 		center, M, cube, cam_para = center.cuda(), M.cuda(), cube.cuda(), cam_para.cuda()
#
# 		t = time.time()
# 		estimation = model(points.transpose(1,2), points.transpose(1,2), img, test_data, center, M, cube, cam_para)
# 		timer += time.time() - t
#
# 	torch.cuda.synchronize()
#
# 	outputs_xyz = estimation.transpose(1,2)
# 	diff = torch.pow(outputs_xyz-gt_xyz, 2).view(-1,opt.JOINT_NUM,3)
# 	diff_sum = torch.sum(diff,2)
# 	diff_sum_sqrt = torch.sqrt(diff_sum)
# 	if opt.dataset == 'nyu' and opt.JOINT_NUM !=14:
# 		diff_sum_sqrt = diff_sum_sqrt[:, calculate]
# 	diff_mean = torch.mean(diff_sum_sqrt,1).view(-1,1)
# 	diff_mean_wld = torch.mul(diff_mean,volume_length.view(-1, 1) / 2 if opt.dataset == "nyu" else 250./2)
# 	test_wld_err = test_wld_err + diff_mean_wld.sum().item()
#
#
# # time taken
# torch.cuda.synchronize()
# # timer = time.time() - timer
# timer = timer / len(test_data)
# print('==> time to learn 1 sample = %f (ms)' %(timer*1000))
#
# # print mse
# print('average estimation error in world coordinate system: ')
# print(test_wld_err/ len(test_data))


# 3. evaluation
torch.cuda.synchronize()

model.eval()
test_mse = 0.0
test_wld_err = 0.0
test_wld_err_mean = 0.0

timer = 0
total_samples = 0

saved_points = []
saved_gt = []
saved_fold1 = []
saved_final = []
saved_error = []
saved_length = []

# 记录开始时间
start_time = time.time()

for i, data in enumerate(tqdm(test_dataloader, 0)):
    torch.cuda.synchronize()
    with torch.no_grad():
        # 3.2.1 load inputs and targets
        if opt.dataset == "nyu":
            img, points, gt_xyz, uvd_gt, center, M, cube, cam_para, volume_length = data
            volume_length = volume_length.cuda()
        else:
            img, points, gt_xyz, uvd_gt, center, M, cube, cam_para = data
            volume_length = 250.

        points, gt_xyz, img = points.cuda(),  gt_xyz.cuda(), img.cuda()
        center, M, cube, cam_para = center.cuda(), M.cuda(), cube.cuda(), cam_para.cuda()

        t = time.time()
        estimation = model(points.transpose(1,2), points.transpose(1,2), img, test_data, center, M, cube, cam_para)
        timer += time.time() - t

        torch.cuda.synchronize()

        outputs_xyz = estimation.transpose(1,2)
        diff = torch.pow(outputs_xyz-gt_xyz, 2).view(-1,opt.JOINT_NUM,3)
        diff_sum = torch.sum(diff,2)
        diff_sum_sqrt = torch.sqrt(diff_sum)
        if opt.dataset == 'nyu' and opt.JOINT_NUM !=14:
            diff_sum_sqrt = diff_sum_sqrt[:, calculate]
        diff_mean = torch.mean(diff_sum_sqrt,1).view(-1,1)
        diff_mean_wld = torch.mul(diff_mean,volume_length.view(-1, 1) / 2 if opt.dataset == "nyu" else 250./2)
        test_wld_err = test_wld_err + diff_mean_wld.sum().item()

        total_samples += points.size(0)  # 假设每个batch的图像数是固定的

torch.cuda.synchronize()
# timer = time.time() - timer
timer = timer / total_samples
print('==> time to learn 1 sample = %f (ms)' %(timer*1000))

# 计算fps
end_time = time.time()
total_time = end_time - start_time
fps = total_samples / total_time
print('==> FPS: %f' % fps)

# print mse
print('average estimation error in world coordinate system: ')
print(test_wld_err/ len(test_data))

