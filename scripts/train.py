# coding=utf-8
from mxnet.gluon import trainer
from datasets.dataloader import ICDAR
from mxnet.gluon.data import DataLoader
from model.net import PSENet
import mxnet as mx
from mxnet.gluon import Trainer
from model.loss import DiceLoss
from mxnet import autograd
import mxboard as mb
from mxnet import lr_scheduler as ls

def train(data_dir, pretrain_model, epoches=3, lr=0.001, batch_size=5, ctx=mx.cpu(), verbose_step=1, ckpt='ckpt'):

    icdar_loader = ICDAR(data_dir=data_dir)
    loader = DataLoader(icdar_loader, batch_size=batch_size, shuffle=True)
    net = PSENet(num_kernels=7, ctx=ctx)
    # initial params
    net.collect_params().initialize(mx.init.Normal(sigma=0.1), ctx=ctx)
    # net.initialize(ctx=ctx)
    # net.load_parameters(pretrain_model, ctx=ctx, allow_missing=True, ignore_extra=True)
    pse_loss = DiceLoss(lam=0.7)

    cos_shc = ls.PolyScheduler(max_update=icdar_loader.length * epoches//batch_size, base_lr=lr)
    trainer = Trainer(net.collect_params(), 'adam', {'learning_rate': lr, 'lr_scheduler':cos_shc})
    summary_writer = mb.SummaryWriter(ckpt)
    for e in range(epoches):
        cumulative_loss = 0

        for i, item in enumerate(loader):
            im, score_maps, kernels, training_masks = item
            im = im.as_in_context(ctx)
            score_maps = score_maps[:, ::4, ::4].as_in_context(ctx)
            kernels = kernels[:, ::4, ::4, :].as_in_context(ctx)
            training_masks = training_masks[:, ::4, ::4].as_in_context(ctx)

            with autograd.record():
                kernels_pred = net(im)
                loss = pse_loss(score_maps, kernels, kernels_pred, training_masks)
                loss.backward()
            trainer.step(batch_size)
            if i%verbose_step==0:
                global_steps = icdar_loader.length * e + i * batch_size
                summary_writer.add_image('score_map', kernels[0:1, 0:1, :, :], global_steps)
                summary_writer.add_image('score_map_pred', kernels_pred[0:1, 0:1, :, :], global_steps)
                summary_writer.add_scalar('loss', mx.nd.mean(loss).asscalar(), global_steps)
                summary_writer.add_scalar('c_loss', mx.nd.mean(pse_loss.C_loss).asscalar(), global_steps)
                summary_writer.add_scalar('kernel_loss', mx.nd.mean(pse_loss.kernel_loss).asscalar(), global_steps)

                print("step: {}, loss: {}".format(i * batch_size, mx.nd.mean(loss).asscalar()))
            cumulative_loss += mx.nd.mean(loss).asscalar()
        print("Epoch {}, loss: {}".format(e, cumulative_loss))
        net.save_parameters(os.path.join(ckpt, 'model_{}.param'.format(e)))
    summary_writer.close()
if __name__ == '__main__':
    import sys
    data_dir = sys.argv[1]
    pretrain_model = sys.argv[2]
    ctx = sys.argv[3]
    if len(sys.argv) < 2:
        print("Usage: python train.py $data_dir $pretrain_model")
    if eval(ctx) >= 0 :
        devices = mx.gpu(eval(ctx))
    else:
        devices = mx.cpu()
    train(data_dir=data_dir, pretrain_model=pretrain_model, ctx=devices)

