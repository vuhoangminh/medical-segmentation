from projects.headneck.loop.loop_utils import run
import unet3d.utils.args_utils as get_args
from unet3d.utils.path_utils import get_model_h5_filename
import random
from unet3d.utils.path_utils import get_project_dir
from projects.headneck.config import config, config_unet
import os
import pprint
pp = pprint.PrettyPrinter(indent=4)

config.update(config_unet)

CURRENT_WORKING_DIR = os.path.realpath(__file__)
PROJECT_DIR = get_project_dir(CURRENT_WORKING_DIR, config["project_name"])
BRATS_DIR = os.path.join(PROJECT_DIR, config["brats_folder"])
DATASET_DIR = os.path.join(PROJECT_DIR, config["dataset_folder"])


model_list = list()
cmd_list = list()
out_file_list = list()

list_25d_model = ["256-256-3", "256-256-5",
                  "256-256-7", "256-256-9", "256-256-11"]
list_2d_model = ["256-256-1"]
list_3d_model = ["256-256-32"]


for patch_shape in list_25d_model + list_2d_model + list_3d_model:
    if patch_shape in list_2d_model:
        args = get_args.train2d_kits()
        task = "projects/headneck/train2d"
        model_dim = 2
        args.batch_size = 16
    elif patch_shape in list_25d_model:
        args = get_args.train25d_kits()
        task = "projects/headneck/train25d"
        model_dim = 25
        args.batch_size = 16
    else:
        args = get_args.train_kits()
        task = "projects/headneck/train"
        model_dim = 3
        args.batch_size = 1

    args.patch_shape = patch_shape
    args.is_test = "0"

    for is_augment in ["1"]:
        args.is_augment = is_augment
        for model_name in ["segnet", "unet"]:
            args.model = model_name
            for is_denoise in ["0"]:
                args.is_denoise = is_denoise
                for is_normalize in ["z"]:
                    args.is_normalize = is_normalize
                    for is_hist_match in ["0"]:
                        args.is_hist_match = is_hist_match
                        for loss in ["weighted"]:
                            if is_normalize == "z" and is_hist_match == "1":
                                continue

                            model_filename = get_model_h5_filename(
                                "model", args)

                            cmd = "python {}.py -t \"{}\" -o \"0\" -n \"{}\" -de \"{}\" -hi \"{}\" -ps \"{}\" -l \"{}\" -m \"{}\" -ba {} -au {} -du 4".format(
                                task,
                                args.is_test,
                                args.is_normalize,
                                args.is_denoise,
                                args.is_hist_match,
                                args.patch_shape,
                                args.loss,
                                args.model,
                                args.batch_size,
                                args.is_augment
                            )

                            model_list.append(model_filename)
                            cmd_list.append(cmd)


combined = list(zip(model_list, cmd_list))
random.shuffle(combined)

model_list[:], cmd_list = zip(*combined)

for i in range(len(model_list)):
    model_filename = model_list[i]
    cmd = cmd_list[i]
    run(model_filename=model_filename, cmd=cmd, config=config,
        model_path="database/model", mode_run=2)
