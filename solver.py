import os
import numpy as np
import time
import datetime
import torch
import torchvision
from torch import optim
from torch.autograd import Variable
import torch.nn.functional as F
from evaluation import Metrics
from network import U_Net,R2U_Net,AttU_Net,R2AttU_Net
import csv
import logging
from PIL import Image

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)


class Solver(object):
	def __init__(self, config, train_loader, valid_loader, test_loader):

		# Data loader
		self.train_loader = train_loader
		self.valid_loader = valid_loader
		self.test_loader = test_loader

		# Models
		self.unet = None
		self.optimizer = None
		self.img_ch = config.img_ch
		self.output_ch = config.output_ch
		self.criterion = torch.nn.BCELoss()
		self.augmentation_prob = config.augmentation_prob

		# Hyper-parameters
		self.lr = config.lr
		self.beta1 = config.beta1
		self.beta2 = config.beta2

		# Training settings
		self.num_epochs = config.num_epochs
		self.num_epochs_decay = config.num_epochs_decay
		self.batch_size = config.batch_size

		# Step size
		self.log_step = config.log_step
		self.val_step = config.val_step

		# Path
		self.model_path = config.model_path
		self.result_path = config.result_path
		self.mode = config.mode

		self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
		self.model_type = config.model_type
		self.t = config.t
		self.build_model()

	def build_model(self):
		"""Build generator and discriminator."""
		if self.model_type =='U_Net':
			self.unet = U_Net(img_ch=3,output_ch=1)
		elif self.model_type =='R2U_Net':
			self.unet = R2U_Net(img_ch=3,output_ch=1,t=self.t)
		elif self.model_type =='AttU_Net':
			self.unet = AttU_Net(img_ch=3,output_ch=1)
		elif self.model_type == 'R2AttU_Net':
			self.unet = R2AttU_Net(img_ch=3,output_ch=1,t=self.t)
			

		self.optimizer = optim.Adam(list(self.unet.parameters()),
									  self.lr, [self.beta1, self.beta2])
		self.unet.to(self.device)

		# self.print_network(self.unet, self.model_type)

	def print_network(self, model, name):
		"""Print out the network information."""
		num_params = 0
		for p in model.parameters():
			num_params += p.numel()
		print(model)
		print(name)
		print("The number of parameters: {}".format(num_params))

	def to_data(self, x):
		"""Convert variable to tensor."""
		if torch.cuda.is_available():
			x = x.cpu()
		return x.data

	def update_lr(self, g_lr, d_lr):
		for param_group in self.optimizer.param_groups:
			param_group['lr'] = lr

	def reset_grad(self):
		"""Zero the gradient buffers."""
		self.unet.zero_grad()

	def compute_accuracy(self,SR,GT):
		SR_flat = SR.view(-1)
		GT_flat = GT.view(-1)

		acc = GT_flat.data.cpu()==(SR_flat.data.cpu()>0.5)

	def tensor2img(self,x):
		img = (x[:,0,:,:]>x[:,1,:,:]).float()
		img = img*255
		return img


	def train(self, lr, epoch):
		self.unet.train(True)
		epoch_loss = 0
		
		metrics = Metrics()
		length = 0

		for i, (images, GT) in enumerate(self.train_loader):
			if i%50==0:
				gt0 = torchvision.transforms.ToPILImage()(GT[0, ...])
				im0 = torchvision.transforms.ToPILImage()(images[0, ...])
				os.makedirs("/content/drive/image_log/train", exist_ok=True)
				gt0.save("/content/drive/image_log/train/{}_gt_or.jpg".format(i))
				im0.save("/content/drive/image_log/train/{}_im.jpg".format(i))

			images = images.to(self.device)
			GT = GT.to(self.device)


			# SR : Segmentation Result
			SR = torch.sigmoid(self.unet(images))
			SR_flat = SR.view(SR.size(0),-1)

			GT_flat = GT.view(GT.size(0),-1)
			loss = self.criterion(SR_flat,GT_flat)
			epoch_loss += loss.item()

			# Backprop + optimize
			self.reset_grad()
			loss.backward()
			self.optimizer.step()

			SR = SR.detach()
			GT = GT.detach()

			delta = Metrics(SR, GT)
			metrics.add(delta)
			length += images.size(0)

			delta.div(images.size(0))
			logging.info('Iteration {}/{}, Loss={:.4f}, {}'.format(
				i+1, len(self.train_loader), loss.item(),str(delta)))

			if i%50==0:
				SR = SR.cpu()
				sr0 = torchvision.transforms.ToPILImage()(SR[0, ...])
				srb = torchvision.transforms.ToPILImage()((SR[0, ...]>0.5).float())
				os.makedirs("/content/drive/image_log/train", exist_ok=True)
				sr0.save("/content/drive/image_log/train/{}_pred.jpg".format(i))
				srb.save("/content/drive/image_log/train/{}_pred_bin.jpg".format(i))
			

		metrics.div(length)
		logging.info('Epoch {}/{}, Loss={:.4f}, {}'.format(
			epoch+1, self.num_epochs, epoch_loss, str(metrics)))


	def validate(self):
		with torch.no_grad():
			self.unet.train(False)
			self.unet.eval()

			metrics = Metrics()
			length=0
			for i, (images, GT) in enumerate(self.valid_loader):
				logging.info("Iteration [{}/{}]".format(i+1, len(self.valid_loader)))

				if i%50==0:
					gt0 = torchvision.transforms.ToPILImage()(GT[0, ...])
					im0 = torchvision.transforms.ToPILImage()(images[0, ...])
					os.makedirs("/content/drive/image_log/valid", exist_ok=True)
					gt0.save("/content/drive/image_log/valid/{}_gt_or.jpg".format(i))
					im0.save("/content/drive/image_log/valid/{}_im.jpg".format(i))

				images = images.to(self.device)
				GT = GT.to(self.device)
				SR = torch.sigmoid(self.unet(images))

				metrics.add(Metrics(SR, GT))
				length += images.size(0)


				if i%50==0:
					SR = SR.cpu()
					sr0 = torchvision.transforms.ToPILImage()(SR[0, ...])
					srb = torchvision.transforms.ToPILImage()((SR[0, ...]>0.5).float())
					os.makedirs("/content/drive/image_log/valid", exist_ok=True)
					sr0.save("/content/drive/image_log/valid/{}_pred.jpg".format(i))
					srb.save("/content/drive/image_log/valid/{}_pred_bin.jpg".format(i))
				
			metrics.div(length)
			unet_score = metrics.JS + metrics.DC

			logging.info('Validation, unet_score={:.4f}'.format(unet_score, str(metrics)))
		

			return unet_score



	def test(self, unet_path):
		with torch.no_grad():
			del self.unet
			self.build_model()
			self.unet.load_state_dict(torch.load(unet_path))
			
			self.unet.train(False)
			self.unet.eval()

			metrics = Metrics()
			length=0
			for i, (images, GT) in enumerate(self.valid_loader):
				logging.info("Iteration [{}/{}]".format(i+1, len(self.valid_loader)))

				images = images.to(self.device)
				GT = GT.to(self.device)
				SR = torch.sigmoid(self.unet(images))
				
				metrics.add(Metrics(SR, GT))
				length += images.size(0)
					
			metrics.div(length)
			unet_score = metrics.JS + metrics.DC

			with open(os.path.join(self.result_path,'result.txt'), 'a', encoding='utf-8', newline='') as f:
				f.write("acc: {} \n".format(metrics.acc)
				f.write("SE: {} \n".format(metrics.SE)
				f.write("SP: {} \n".format(metrics.SP)
				f.write("PC: {} \n".format(metrics.PC)
				f.write("F1: {} \n".format(metrics.F1)
				f.write("JS: {} \n".format(metrics.JS)
				f.write("DC: {} \n".format(metrics.DC)
				f.write("unet_score: {} \n".format(unet_score)


	def run(self):
		"""Train encoder, generator and discriminator."""
		
		unet_path = os.path.join(self.model_path, 'best_model.pkl')


		logging.info("Unet path: {}".format(unet_path))

		if os.path.exists(unet_path):
			logging.warning("model file exists, test only")
			self.unet.load_state_dict(torch.load(unet_path))
			logging.info('{} is Successfully Loaded from {}'.format(self.model_type,unet_path))
			# Test
			self.test(unet_path)
		else:
			lr = self.lr
			best_unet_score = 0.

			self.validate()
			
			for epoch in range(self.num_epochs):
				# train
				self.train(lr, epoch)
				
				# Decay lr
				if (epoch+1) > (self.num_epochs - self.num_epochs_decay):
					lr -= (self.lr / float(self.num_epochs_decay))
					for param_group in self.optimizer.param_groups:
						param_group['lr'] = lr
					print ('Decay learning rate to lr: {}.'.format(lr))
				
				# val
				unet_score = self.validate()

				# Save Best U-Net model
				if unet_score > best_unet_score:
					best_unet_score = unet_score
					best_epoch = epoch
					best_unet = self.unet.state_dict()
					print('Best %s model score : %.4f'%(self.model_type,best_unet_score))
					torch.save(best_unet,unet_path)
		
		
