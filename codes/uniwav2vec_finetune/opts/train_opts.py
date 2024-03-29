from .base_opts import BaseOptions
import os, json

class TrainOptions(BaseOptions):
    """This class includes training options.

    It also includes shared options defined in BaseOptions.
    """

    def initialize(self, parser):
        parser = BaseOptions.initialize(self, parser)
        # network saving and loading parameters
        parser.add_argument('--print_freq', type=int, default=100, help='frequency of showing training results on console')
        parser.add_argument('--save_latest_freq', type=int, default=1000, help='frequency of saving the latest results')
        parser.add_argument('--save_epoch_freq', type=int, default=1, help='frequency of saving checkpoints at the end of epochs')
        parser.add_argument('--save_by_iter', action='store_true', help='whether saves model by iteration')
        parser.add_argument('--continue_train', action='store_true', help='continue training: load the latest model')
        parser.add_argument('--epoch_count', type=int, default=1, help='the starting epoch count, we save the model by <epoch_count>, <epoch_count>+<save_latest_freq>, ...')
        parser.add_argument('--phase', type=str, default='train', help='train, val, test, etc')

        # training parameters
        parser.add_argument('--niter', type=int, default=20, help='# of iter at starting learning rate')
        parser.add_argument('--niter_decay', type=int, default=80, help='# of iter to linearly decay learning rate to zero')
        parser.add_argument('--beta1', type=float, default=0.5, help='momentum term of adam')
        parser.add_argument('--lr', type=float, default=2e-4, help='initial learning rate for adam')
        parser.add_argument('--lr_policy', type=str, default='linear', help='learning rate policy. [linear | step | plateau | cosine]')
        parser.add_argument('--lr_decay_iters', type=int, default=50, help='multiply by a gamma every lr_decay_iters iterations')

        # warm-up
        parser.add_argument('--warmup', action='store_true', help='# whether to do warmup')
        parser.add_argument('--warmup_epoch', type=int, default=5, help='# of epoch to warmup the network')
        parser.add_argument('--warmup_lr', type=float, default=1e-8, help='# lr used in warmup procedure')

        # expr setting 
        parser.add_argument('--run_idx', type=int, default=1, help='experiment number; for repeat experiment')
        self.isTrain = True
        return parser
    
    def save_json(self, opt, output_dir):
        dictionary = {}
        for k, v in sorted(vars(opt).items()):
            dictionary[k] = v
        save_path = os.path.join(output_dir, '{}_opt.conf'.format(opt.phase))
        json.dump(dictionary, open(save_path, 'w'), indent=4)