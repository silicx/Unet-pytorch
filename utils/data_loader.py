import os
import random
import h5py
from random import shuffle
import numpy as np
import torch
from torch.utils import data
from torchvision import transforms as T
from torchvision.transforms import functional as F
from PIL import Image

class ImageFolder(data.Dataset):
	def __init__(self, root,image_size=224,mode='train',augmentation_prob=0.4):
		"""Initializes image paths and preprocessing module."""
		self.root = root
		
		# GT : Ground Truth
		self.GT_paths = root[:-1]+'_GT/'
		self.image_paths = list(map(lambda x: os.path.join(root, x), os.listdir(root)))
		self.image_size = image_size
		self.mode = mode
		self.RotationDegree = [0,90,180,270]
		self.augmentation_prob = augmentation_prob
		print("image count in {} path :{}".format(self.mode,len(self.image_paths)))

	def __getitem__(self, index):
		"""Reads an image from a file and preprocesses it and returns."""
		image_path = self.image_paths[index]
		filename = image_path.split('_')[-1][:-len(".jpg")]
		GT_path = self.GT_paths + 'ISIC_' + filename + '_segmentation.png'

		image = Image.open(image_path)
		GT = Image.open(GT_path)

		aspect_ratio = image.size[1]/image.size[0]

		Transform = []

		ResizeRange = random.randint(300,320)
		Transform.append(T.Resize((int(ResizeRange*aspect_ratio),ResizeRange)))
		p_transform = random.random()

		if (self.mode == 'train') and p_transform <= self.augmentation_prob:
			RotationDegree = random.randint(0,3)
			RotationDegree = self.RotationDegree[RotationDegree]
			if (RotationDegree == 90) or (RotationDegree == 270):
				aspect_ratio = 1/aspect_ratio

			Transform.append(T.RandomRotation((RotationDegree,RotationDegree)))
						
			RotationRange = random.randint(-10,10)
			Transform.append(T.RandomRotation((RotationRange,RotationRange)))
			CropRange = random.randint(250,270)
			Transform.append(T.CenterCrop((int(CropRange*aspect_ratio),CropRange)))
			Transform = T.Compose(Transform)
			
			image = Transform(image)
			GT = Transform(GT)

			ShiftRange_left = random.randint(0,20)
			ShiftRange_upper = random.randint(0,20)
			ShiftRange_right = image.size[0] - random.randint(0,20)
			ShiftRange_lower = image.size[1] - random.randint(0,20)
			image = image.crop(box=(ShiftRange_left,ShiftRange_upper,ShiftRange_right,ShiftRange_lower))
			GT = GT.crop(box=(ShiftRange_left,ShiftRange_upper,ShiftRange_right,ShiftRange_lower))

			if random.random() < 0.5:
				image = F.hflip(image)
				GT = F.hflip(GT)

			if random.random() < 0.5:
				image = F.vflip(image)
				GT = F.vflip(GT)

			Transform = T.ColorJitter(brightness=0.2,contrast=0.2,hue=0.02)

			image = Transform(image)

			Transform =[]


		Transform.append(T.Resize((int(256*aspect_ratio)-int(256*aspect_ratio)%16,256)))
		Transform.append(T.ToTensor())
		Transform = T.Compose(Transform)
		
		image = Transform(image)
		GT = Transform(GT)

		Norm_ = T.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
		image = Norm_(image)

		return image, GT

	def __len__(self):
		"""Returns the total number of font files."""
		return len(self.image_paths)







class H5pyDataset(data.Dataset):
	def __init__(self, root, exp_name, image_size=224,mode='train',augmentation_prob=0.):
		"""Initializes image paths and preprocessing module."""
		self.root = root
		
		# GT : Ground Truth
		self.image_paths = list(map(lambda x: os.path.join(root, x), os.listdir(root)))
		self.image_size = image_size
		self.mode = mode
		self.RotationDegree = [0,90,180,270]
		self.augmentation_prob = augmentation_prob

		assert exp_name in ['axis0', 'axis1', 'axis2']
		self.exp_name = exp_name

		print("image count in {} path :{}".format(self.mode,len(self.image_paths)))

	def __getitem__(self, index):
		"""Reads an image from a file and preprocesses it and returns."""
		image_path = self.image_paths[index]
		fp = h5py.File(image_path, "r")
		if len(fp['data'].shape) == 2:
			n_channel = 1
		else:
			n_channel = fp['data'].shape[2]

		image = np.array(fp['data'])
		#image = (((image>70)&(image<140))*255)
		image = Image.fromarray(image.astype(np.uint8))
		gt    = np.array(fp['annot'])
		gt    = gt*255
		gt    = Image.fromarray(gt.astype(np.uint8))
		fp.close()

		#if self.exp_name == 'axis0':
		#	image = T.functional.crop(image, 100, 122, 256, 256)
		#	gt    = T.functional.crop(gt   , 100, 122, 256, 256)


		image = T.ToTensor()(image)
		image = T.Normalize((.5,)*n_channel, (.5,)*n_channel)(image)
		gt    = T.ToTensor()(gt)

		return image, gt

	def __len__(self):
		"""Returns the total number of font files."""
		return len(self.image_paths)



def get_loader(exp_name, image_path, image_size, batch_size, num_workers=2, mode='train',augmentation_prob=0.4):
	"""Builds and returns Dataloader."""
	
	dataset = H5pyDataset(exp_name = exp_name, root = image_path, image_size =image_size, mode=mode,augmentation_prob=augmentation_prob)
	data_loader = data.DataLoader(dataset=dataset,
								  batch_size=batch_size,
								  shuffle=True,
								  num_workers=num_workers)
	return data_loader