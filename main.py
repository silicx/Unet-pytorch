import logging, h5py
import numpy as np
from PIL import Image
import torchvision.transforms as T

import utils.solver
from data_loader import get_loader
from utils.network import U_Net


def train(config):
    cudnn.benchmark = True
    if config.model_type not in ['U_Net','R2U_Net','AttU_Net','R2AttU_Net']:
        print('ERROR!! model_type should be selected in U_Net/R2U_Net/AttU_Net/R2AttU_Net')
        print('Your input for model_type was %s'%config.model_type)
        return

    # Create directories if not exist
    if not os.path.exists(config.model_path):
        os.makedirs(config.model_path)
    if not os.path.exists(config.result_path):
        os.makedirs(config.result_path)
    config.result_path = os.path.join(config.result_path,config.model_type)
    if not os.path.exists(config.result_path):
        os.makedirs(config.result_path)

    logging.info(config)
        
    train_loader = get_loader(config, mode='train')
    valid_loader = get_loader(config, mode='valid')
    test_loader = get_loader(config, mode='test')

    solve = utils.solver.Solver(config, train_loader, valid_loader, test_loader)

    
    # Train and sample the images
    if config.mode == 'train':
        solve.run()
    elif config.mode == 'test':
        solve.test()


def test_3D(config, data_dir, save_dir):
    """
    produce the inference result of 3D images
    :config: instance of class 'Configuration'
    :data_dir: directory of test set (case1.h5~case10.h5)
    :save_dir: directory of output
    """

    unet_path = os.path.join(config.model_path, 'best_model.pkl')
    assert os.path.exists(unet_path)

    save_path = os.path.join(save_dir, config.name)
    os.makedirs(save_path, exist_ok=True)


    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    unet = U_Net(img_ch=config.img_ch,output_ch=config.output_ch)
    unet.load_state_dict(torch.load(unet_path))
    unet.to(device)
    logging.info('Weight loaded: {}'.format(unet_path))

    for fname in os.listdir(data_dir):
        logging.info('Sample {}'.format(fname))
        with h5py.File(os.path.join(data_dir, fname), 'r') as fp:
            data = np.array(fp['data'])
        data = data[data.shape[0]%16 :, ...]
        
        if config.name == 'axis1':
            data = data.transpose((1,0,2))
        elif config.name == 'axis2':
            data = data.transpose((2,0,1))
        
        res = []
        
        for i in range(data.shape[0]):
            if i%100==99:
                logging.info("[{}/{}]".format(i+1, data.shape[0]))
                
            img = data[i,...]
            img = Image.fromarray(img)
            img = T.ToTensor()(img)
            img = T.Normalize((.5,), (.5,))(img)
            img = img.view(1,img.size(0), img.size(1))
            
            with torch.no_grad():
                unet.train(False)
                unet.eval()
                img = img.to(device)
                pred = torch.Softmax(dim=1)(unet(img))
                pred = pred[0,...]
                pred = torch.argmax(pred, dim=0)
                pred = pred.cpu().numpy()
                res.append(pred)
        
        data = np.concatenate(res, axis=0)
        logging.info(data.shape)
        
        if config.name == 'axis1':
            data = data.transpose((1,0,2))
        elif config.name == 'axis2':
            data = data.transpose((1,2,0))
            
        with h5py.File(os.path.join(save_path, fname), 'w') as fp:
            fp['data'] = data