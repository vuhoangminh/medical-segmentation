import os
import copy
from random import shuffle
import itertools

import numpy as np
import time

from unet3d.utils import pickle_dump, pickle_load
from unet3d.generator import get_train_valid_test_split, get_number_of_steps
from unet3d.generator import get_multi_class_labels, get_data_from_file
from unet3d.generator import get_train_valid_test_split_isbr
from unet3d.generator import add_data
from unet3d.utils.patches import compute_patch_indices, get_random_nd_index

import tensorlayer as tl
from scipy.ndimage.filters import gaussian_filter
from scipy.ndimage.interpolation import map_coordinates

from unet3d.utils.threadsafe import threadsafe_generator

# from unet3d.generator import get_training_and_validation_and_testing_generators


def get_training_and_validation_and_testing_generators25d(data_file, batch_size, n_labels, training_keys_file,
                                                          validation_keys_file, testing_keys_file,
                                                          data_split=0.8, overwrite=False, labels=None, patch_shape=None,
                                                          validation_patch_overlap=0, training_patch_start_offset=None,
                                                          validation_batch_size=None,
                                                          patch_overlap=[0, 0, -1],
                                                          project="brats",
                                                          augment_flipud=False, augment_fliplr=False, augment_elastic=False,
                                                          augment_rotation=False, augment_shift=False, augment_shear=False,
                                                          augment_zoom=False, n_augment=0, skip_blank=False, is_test="1"):
    """
    Creates the training and validation generators that can be used when training the model.
    :param skip_blank: If True, any blank (all-zero) label images/patches will be skipped by the data generator.
    :param validation_batch_size: Batch size for the validation data.
    :param training_patch_start_offset: Tuple of length 3 containing integer values. Training data will randomly be
    offset by a number of pixels between (0, 0, 0) and the given tuple. (default is None)
    :param validation_patch_overlap: Number of pixels/voxels that will be overlapped in the validation data. (requires
    patch_shape to not be None)
    :param patch_shape: Shape of the data to return with the generator. If None, the whole image will be returned.
    (default is None)
    :param augment_flip: if True and augment is True, then the data will be randomly flipped along the x, y and z axis
    :param augment_distortion_factor: if augment is True, this determines the standard deviation from the original
    that the data will be distorted (in a stretching or shrinking fashion). Set to None, False, or 0 to prevent the
    augmentation from distorting the data in this way.
    :param augment: If True, training data will be distorted on the fly so as to avoid over-fitting.
    :param labels: List or tuple containing the ordered label values in the image files. The length of the list or tuple
    should be equal to the n_labels value.
    Example: (10, 25, 50)
    The data generator would then return binary truth arrays representing the labels 10, 25, and 30 in that order.
    :param data_file: hdf5 file to load the data from.
    :param batch_size: Size of the batches that the training generator will provide.
    :param n_labels: Number of binary labels.
    :param training_keys_file: Pickle file where the index locations of the training data will be stored.
    :param validation_keys_file: Pickle file where the index locations of the validation data will be stored.
    :param data_split: How the training and validation data will be split. 0 means all the data will be used for
    validation and none of it will be used for training. 1 means that all the data will be used for training and none
    will be used for validation. Default is 0.8 or 80%.
    :param overwrite: If set to True, previous files will be overwritten. The default mode is false, so that the
    training and validation splits won't be overwritten when rerunning model training.
    :param permute: will randomly permute the data (data must be 3D cube)
    :return: Training data generator, validation data generator, number of training steps, number of validation steps
    """

    if not validation_batch_size:
        validation_batch_size = batch_size

    if project == "brats":
        training_list, validation_list, _ = get_train_valid_test_split(
            data_file, training_file=training_keys_file,
            validation_file=validation_keys_file,
            testing_file=testing_keys_file,
            data_split=data_split, overwrite=False)
    else:
        training_list, validation_list, _ = get_train_valid_test_split_isbr(
            data_file, training_file=training_keys_file,
            validation_file=validation_keys_file,
            testing_file=testing_keys_file,
            overwrite=False)

    print("training_list:", training_list)
    # train_patch_overlap = np.asarray([0, 0, patch_shape[-1]-2])
    # valid_patch_overlap = np.asarray([0, 0, patch_shape[-1]-1])
    train_patch_overlap = np.asarray([0, 0, patch_shape[-1]-1])
    valid_patch_overlap = np.asarray([0, 0, patch_shape[-1]-1])

    print(">> training data generator")
    training_generator = data_generator25d(data_file, training_list,
                                           batch_size=batch_size,
                                           n_labels=n_labels,
                                           labels=labels,
                                           patch_shape=patch_shape,
                                           patch_overlap=train_patch_overlap,
                                           patch_start_offset=training_patch_start_offset,
                                           augment_flipud=augment_flipud,
                                           augment_fliplr=augment_fliplr,
                                           augment_elastic=augment_elastic,
                                           augment_rotation=augment_rotation,
                                           augment_shift=augment_shift,
                                           augment_shear=augment_shear,
                                           augment_zoom=augment_zoom,
                                           n_augment=n_augment,
                                           skip_blank=skip_blank)
    print(">> valid data generator")
    validation_generator = data_generator25d(data_file, validation_list,
                                             batch_size=validation_batch_size,
                                             n_labels=n_labels,
                                             labels=labels,
                                             patch_shape=patch_shape,
                                             patch_overlap=valid_patch_overlap,
                                             skip_blank=skip_blank
                                             )

    print(">> compute number of training and validation steps")

    # num_training_steps = get_number_of_steps(get_number_of_patches25d(data_file, training_list, patch_shape,
    #                                                                     patch_start_offset=training_patch_start_offset,
    #                                                                     patch_overlap=train_patch_overlap),
    #                                             batch_size)
    # num_validation_steps = get_number_of_steps(get_number_of_patches25d(data_file, validation_list, patch_shape,
    #                                                                     patch_overlap=valid_patch_overlap),
    #                                            validation_batch_size)

    # num_training_steps = get_number_of_steps(11200, batch_size)
    # num_validation_steps = get_number_of_steps(2794, validation_batch_size)

    from unet3d.generator import get_number_of_patches
    num_training_steps = get_number_of_steps(get_number_of_patches(data_file, training_list, patch_shape,
                                                                   patch_start_offset=training_patch_start_offset,
                                                                   patch_overlap=train_patch_overlap),
                                             batch_size)
    num_validation_steps = get_number_of_steps(get_number_of_patches(data_file, validation_list, patch_shape,
                                                                     patch_overlap=valid_patch_overlap),
                                               validation_batch_size)

    print("Number of training steps: ", num_training_steps)
    print("Number of validation steps: ", num_validation_steps)

    return training_generator, validation_generator, num_training_steps, num_validation_steps


def create_patch_index_list(index_list, image_shape, patch_shape, patch_overlap, patch_start_offset=None):
    patch_index = list()
    for index in index_list:
        if patch_start_offset is not None:
            random_start_offset = np.negative(
                get_random_nd_index(patch_start_offset))
            patches = compute_patch_indices(image_shape, patch_shape,
                                            overlap=patch_overlap, start=random_start_offset,
                                            is_extract_patch_agressive=True)
        else:
            patches = compute_patch_indices(image_shape, patch_shape,
                                            overlap=patch_overlap,
                                            is_extract_patch_agressive=True)
        patch_index.extend(itertools.product([index], patches))
    return patch_index


@threadsafe_generator
def data_generator25d(data_file, index_list, batch_size=1, n_labels=1, labels=None, patch_shape=None,
                      patch_overlap=0, patch_start_offset=None, shuffle_index_list=True,
                      skip_blank=True,
                      augment_flipud=False, augment_fliplr=False, augment_elastic=False,
                      augment_rotation=False, augment_shift=False, augment_shear=False,
                      augment_zoom=False, n_augment=False):
    orig_index_list = index_list
    while True:
        x_list = list()
        y_list = list()
        if patch_shape:
            index_list = create_patch_index_list(orig_index_list, data_file.root.data.shape[-3:], patch_shape,
                                                 patch_overlap, patch_start_offset)
        else:
            index_list = copy.copy(orig_index_list)

        if shuffle_index_list:
            shuffle(index_list)
        while len(index_list) > 0:
            index = index_list.pop()
            add_data(x_list, y_list, data_file, index, patch_shape=patch_shape,
                     augment_flipud=augment_flipud, augment_fliplr=augment_fliplr,
                     augment_elastic=False, augment_rotation=augment_rotation,
                     augment_shift=augment_shift, augment_shear=augment_shear,
                     augment_zoom=augment_zoom, model_dim=25)

            if len(x_list) == batch_size or (len(index_list) == 0 and len(x_list) > 0):
                yield convert_data25d(x_list, y_list, n_labels=n_labels, labels=labels)
                x_list = list()
                y_list = list()


def get_number_of_patches25d(data_file, index_list, patch_shape=None, patch_overlap=0, patch_start_offset=None,
                             skip_blank=True):
    if patch_shape:
        index_list = create_patch_index_list(index_list, data_file.root.data.shape[-3:], patch_shape, patch_overlap,
                                             patch_start_offset)
        count = 0
        for i, index in enumerate(index_list, 0):
            if i % 50 == 0 and i > 0:
                print(">> processing {}/{}, added {}/{}".format(i,
                                                                len(index_list), count, len(index_list)))
            x_list = list()
            y_list = list()
            add_data(x_list, y_list, data_file, index,
                     skip_blank=skip_blank, patch_shape=patch_shape,
                     model_dim=25)
            if len(x_list) > 0:
                count += 1
        return count
    else:
        return len(index_list)


def convert_data25d(x_list, y_list, n_labels=1, labels=None):
    x = np.asarray(x_list)
    y = np.asarray(y_list)
    if n_labels == 1:
        y[y > 0] = 1
    elif n_labels > 1:
        y = get_multi_class_labels(y, n_labels=n_labels, labels=labels)
    slice_gt = y.shape[-1]//2
    return x, y[..., slice_gt]
