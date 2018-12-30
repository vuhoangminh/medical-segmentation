import os
import copy
from random import shuffle
import itertools

import numpy as np
import time

from unet3d.utils import pickle_dump, pickle_load
from unet3d.utils.patches import compute_patch_indices, get_random_nd_index, get_patch_from_3d_data
from unet3d.augment import augment_data, random_permutation_x_y

import tensorlayer as tl
from scipy.ndimage.filters import gaussian_filter
from scipy.ndimage.interpolation import map_coordinates


def get_training_and_validation_and_testing_generators(data_file, batch_size, n_labels, training_keys_file,
                                                       validation_keys_file, testing_keys_file,
                                                       data_split=0.8, overwrite=False, labels=None, patch_shape=None,
                                                       validation_patch_overlap=0, training_patch_start_offset=None,
                                                       validation_batch_size=None, is_create_patch_index_list_original=True,
                                                       augment_flipud=False, augment_fliplr=False, augment_elastic=False,
                                                       augment_rotation=False, augment_shift=False, augment_shear=False,
                                                       augment_zoom=False, n_augment=0, skip_blank=False,):
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

    training_list, validation_list, testing_list = get_train_valid_test_split(
        data_file, training_file=training_keys_file,
        validation_file=validation_keys_file,
        testing_file=testing_keys_file,
        data_split=0.8, overwrite=False)

    print("training_list:", training_list)

    print(">> training data generator")
    training_generator = data_generator_new(data_file, training_list,
                                            batch_size=batch_size,
                                            n_labels=n_labels,
                                            labels=labels,
                                            patch_shape=patch_shape,
                                            patch_overlap=0,
                                            patch_start_offset=training_patch_start_offset,
                                            is_create_patch_index_list_original=is_create_patch_index_list_original,
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
    validation_generator = data_generator_new(data_file, validation_list,
                                              batch_size=validation_batch_size,
                                              n_labels=n_labels,
                                              labels=labels,
                                              patch_shape=patch_shape,
                                              patch_overlap=validation_patch_overlap,
                                              is_create_patch_index_list_original=is_create_patch_index_list_original,
                                              skip_blank=skip_blank
                                              )

    # Set the number of training and testing samples per epoch correctly
    # if overwrite or not os.path.exists(n_steps_file):
    print(">> compute number of training and validation steps")
    num_training_steps = get_number_of_steps(get_number_of_patches_new(data_file, training_list, patch_shape,
                                                                       patch_start_offset=training_patch_start_offset,
                                                                       patch_overlap=0, skip_blank=skip_blank,
                                                                       augment_flipud=augment_flipud,
                                                                       augment_fliplr=augment_fliplr,
                                                                       augment_elastic=augment_elastic,
                                                                       augment_rotation=augment_rotation,
                                                                       augment_shift=augment_shift,
                                                                       augment_shear=augment_shear,
                                                                       augment_zoom=augment_zoom,),
                                             batch_size)
    num_validation_steps = get_number_of_steps(get_number_of_patches_new(data_file, validation_list, patch_shape,
                                                                         patch_overlap=validation_patch_overlap, skip_blank=skip_blank,
                                                                         augment_flipud=augment_flipud,
                                                                         augment_fliplr=augment_fliplr,
                                                                         augment_elastic=augment_elastic,
                                                                         augment_rotation=augment_rotation,
                                                                         augment_shift=augment_shift,
                                                                         augment_shear=augment_shear,
                                                                         augment_zoom=augment_zoom,),
                                               validation_batch_size)

    print("Number of training steps: ", num_training_steps)
    print("Number of validation steps: ", num_validation_steps)

    return training_generator, validation_generator, num_training_steps, num_validation_steps


def get_training_and_validation_generators(data_file, batch_size, n_labels, training_keys_file, validation_keys_file,
                                           data_split=0.8, overwrite=False, labels=None, augment=False,
                                           augment_flip=True, augment_distortion_factor=0.25, patch_shape=None,
                                           validation_patch_overlap=0, training_patch_start_offset=None,
                                           validation_batch_size=None, skip_blank=True, permute=False):
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

    training_list, validation_list = get_validation_split(data_file,
                                                          data_split=data_split,
                                                          overwrite=overwrite,
                                                          training_file=training_keys_file,
                                                          validation_file=validation_keys_file)

    training_generator = data_generator(data_file, training_list,
                                        batch_size=batch_size,
                                        n_labels=n_labels,
                                        labels=labels,
                                        augment=augment,
                                        augment_flip=augment_flip,
                                        augment_distortion_factor=augment_distortion_factor,
                                        patch_shape=patch_shape,
                                        patch_overlap=0,
                                        patch_start_offset=training_patch_start_offset,
                                        skip_blank=skip_blank,
                                        permute=permute)
    validation_generator = data_generator(data_file, validation_list,
                                          batch_size=validation_batch_size,
                                          n_labels=n_labels,
                                          labels=labels,
                                          patch_shape=patch_shape,
                                          patch_overlap=validation_patch_overlap,
                                          skip_blank=skip_blank)

    # Set the number of training and testing samples per epoch correctly
    num_training_steps = get_number_of_steps(get_number_of_patches(data_file, training_list, patch_shape,
                                                                   skip_blank=skip_blank,
                                                                   patch_start_offset=training_patch_start_offset,
                                                                   patch_overlap=0), batch_size)
    print("Number of training steps: ", num_training_steps)

    num_validation_steps = get_number_of_steps(get_number_of_patches(data_file, validation_list, patch_shape,
                                                                     skip_blank=skip_blank,
                                                                     patch_overlap=validation_patch_overlap),
                                               validation_batch_size)
    print("Number of validation steps: ", num_validation_steps)

    return training_generator, validation_generator, num_training_steps, num_validation_steps


from unet3d.generator import get_number_of_steps, get_train_valid_test_split, split_list


def data_generator(data_file, index_list, batch_size=1, n_labels=1, labels=None, augment=False, augment_flip=True,
                   augment_distortion_factor=0.25, patch_shape=None, patch_overlap=0, patch_start_offset=None,
                   shuffle_index_list=True, skip_blank=True, permute=False):
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
            add_data(x_list, y_list, data_file, index, augment=augment, augment_flip=augment_flip,
                     augment_distortion_factor=augment_distortion_factor, patch_shape=patch_shape,
                     skip_blank=skip_blank, permute=permute)
            if len(x_list) == batch_size or (len(index_list) == 0 and len(x_list) > 0):
                yield convert_data(x_list, y_list, n_labels=n_labels, labels=labels)
                x_list = list()
                y_list = list()


def data_generator_new(data_file, index_list, batch_size=1, n_labels=1, labels=None, patch_shape=None,
                       patch_overlap=0, patch_start_offset=None, shuffle_index_list=True,
                       skip_blank=True, is_create_patch_index_list_original=True,
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
            add_data_new(x_list, y_list, data_file, index, patch_shape=patch_shape,
                         augment_flipud=augment_flipud, augment_fliplr=augment_fliplr,
                         augment_elastic=augment_elastic, augment_rotation=augment_rotation,
                         augment_shift=augment_shift, augment_shear=augment_shear,
                         augment_zoom=augment_zoom)

            if len(x_list) == batch_size or (len(index_list) == 0 and len(x_list) > 0):
                yield convert_data(x_list, y_list, n_labels=n_labels, labels=labels)
                x_list = list()
                y_list = list()


def get_number_of_patches_new(data_file, index_list, patch_shape=None, patch_overlap=0, patch_start_offset=None,
                              skip_blank=True, augment_flipud=False, augment_fliplr=False, augment_elastic=False,
                              augment_rotation=False, augment_shift=False, augment_shear=False,
                              augment_zoom=False):
    if patch_shape:
        index_list = create_patch_index_list(index_list, data_file.root.data.shape[-3:], patch_shape, patch_overlap,
                                             patch_start_offset)

        return len(index_list)
        # count = 0
        # for index in index_list:
        #     x_list = list()
        #     y_list = list()
        #     add_data_new(x_list, y_list, data_file, index, patch_shape=patch_shape,
        #                  augment_flipud=augment_flipud, augment_fliplr=augment_fliplr,
        #                  augment_elastic=augment_elastic, augment_rotation=augment_rotation,
        #                  augment_shift=augment_shift, augment_shear=augment_shear,
        #                  augment_zoom=augment_zoom, skip_blank=skip_blank)
        #     if len(x_list) > 0:
        #         count += 1
        # return count
    else:
        return len(index_list)


def get_number_of_patches(data_file, index_list, patch_shape=None, patch_overlap=0, patch_start_offset=None,
                          skip_blank=True):
    if patch_shape:
        index_list = create_patch_index_list(index_list, data_file.root.data.shape[-3:], patch_shape, patch_overlap,
                                             patch_start_offset)
        count = 0
        for index in index_list:
            x_list = list()
            y_list = list()
            add_data(x_list, y_list, data_file, index,
                     skip_blank=skip_blank, patch_shape=patch_shape)
            if len(x_list) > 0:
                count += 1
        return count
    else:
        return len(index_list)


def create_patch_index_list(index_list, image_shape, patch_shape, patch_overlap, patch_start_offset=None):
    patch_index = list()
    for index in index_list:
        if patch_start_offset is not None:
            random_start_offset = np.negative(
                get_random_nd_index(patch_start_offset))
            patches = compute_patch_indices(image_shape, patch_shape,
                                            overlap=patch_overlap, start=random_start_offset,
                                            is_extract_patch_agressive=False)
        else:
            patches = compute_patch_indices(image_shape, patch_shape,
                                            overlap=patch_overlap,
                                            is_extract_patch_agressive=False)
        patch_index.extend(itertools.product([index], patches))
    return patch_index


def get_data_from_file(data_file, index, patch_shape=None):
    if patch_shape:
        index, patch_index = index
        data, truth = get_data_from_file(data_file, index, patch_shape=None)
        x = get_patch_from_3d_data(data, patch_shape, patch_index)
        y = get_patch_from_3d_data(truth, patch_shape, patch_index)
    else:
        x, y = data_file.root.data[index], data_file.root.truth[index, 0]
    return x, y


def convert_data(x_list, y_list, n_labels=1, labels=None):
    x = np.asarray(x_list)
    y = np.asarray(y_list)
    if n_labels == 1:
        y[y > 0] = 1
    elif n_labels > 1:
        y = get_multi_class_labels(y, n_labels=n_labels, labels=labels)
    return x, y


def get_multi_class_labels(data, n_labels, labels=None):
    """
    Translates a label map into a set of binary labels.
    :param data: numpy array containing the label map with shape: (n_samples, 1, ...).
    :param n_labels: number of labels.
    :param labels: integer values of the labels.
    :return: binary numpy array of shape: (n_samples, n_labels, ...)
    """
    new_shape = [data.shape[0], n_labels] + list(data.shape[2:])
    y = np.zeros(new_shape, np.int8)
    for label_index in range(n_labels):
        if labels is not None:
            y[:, label_index][data[:, 0] == labels[label_index]] = 1
        else:
            y[:, label_index][data[:, 0] == (label_index + 1)] = 1
    return y


def elastic_transform_multi(x, alpha, sigma, mode="constant", cval=0, is_random=False):
    """Elastic transformation for images as described in `[Simard2003] <http://deeplearning.cs.cmu.edu/pdfs/Simard.pdf>`__.

    Parameters
    -----------
    x : list of numpy.array
        List of greyscale images.
    others : args
        See ``tl.prepro.elastic_transform``.

    Returns
    -------
    numpy.array
        A list of processed images.

    """
    if is_random is False:
        random_state = np.random.RandomState(None)
    else:
        random_state = np.random.RandomState(int(time.time()))

    shape = x[0].shape
    if len(shape) == 4:
        shape = (shape[0], shape[1], shape[2])
    new_shape = random_state.rand(*shape)

    results = []
    for data in x:
        is_4d = False
        if len(data.shape) == 4 and data.shape[-1] == 1:
            data = data[:, :, :, 0]
            is_4d = True
        elif len(data.shape) == 4 and data.shape[-1] != 1:
            raise Exception("Only support greyscale image")

        if len(data.shape) != 3:
            raise AssertionError("input should be grey-scale image")

        dx = gaussian_filter((new_shape * 2 - 1), sigma,
                             mode=mode, cval=cval) * alpha
        dy = gaussian_filter((new_shape * 2 - 1), sigma,
                             mode=mode, cval=cval) * alpha
        dz = np.zeros_like(dx)

        x_, y_, z_ = np.meshgrid(
            np.arange(shape[0]), np.arange(shape[1]), np.arange(shape[2]))

        indices = np.reshape(y_+dy, (-1, 1)), np.reshape(x_+dx,
                                                         (-1, 1)), np.reshape(z_+dz, (-1, 1))

        # tl.logging.info(data.shape)
        if is_4d:
            results.append(map_coordinates(
                data, indices, order=1).reshape((shape[0], shape[1], 1)))
        else:
            results.append(map_coordinates(
                data, indices, order=1).reshape(shape))
    return np.asarray(results)


def augment_data_new(data, augment_flipud=False, augment_fliplr=False, augment_elastic=False,
                     augment_rotation=False, augment_shift=False, augment_shear=False, augment_zoom=False):
    """ data augumentation """
    if augment_flipud:
        data = tl.prepro.flip_axis_multi(
            data, axis=0, is_random=True)  # up down
    if augment_fliplr:
        data = tl.prepro.flip_axis_multi(
            data, axis=1, is_random=True)  # left right
    if augment_elastic:
        data = elastic_transform_multi(
            data, alpha=720, sigma=10, is_random=True)
    if augment_rotation:
        data = tl.prepro.rotation_multi(
            data, rg=20, is_random=True, fill_mode='constant')  # nearest, constant
    if augment_shift:
        data = tl.prepro.shift_multi(
            data, wrg=0.10, hrg=0.10, is_random=True, fill_mode='constant')
    if augment_shear:
        data = tl.prepro.shear_multi(
            data, 0.05, is_random=True, fill_mode='constant')
    if augment_zoom:
        data = tl.prepro.zoom_multi(
            data, zoom_range=[0.9, 1.1], is_random=True, fill_mode='constant')
    return data


def add_data_new(x_list, y_list, data_file, index, patch_shape=None,
                 augment_flipud=False, augment_fliplr=False, augment_elastic=False,
                 augment_rotation=False, augment_shift=False, augment_shear=False,
                 augment_zoom=False, skip_blank=True):
    """
    Adds data from the data file to the given lists of feature and target data
    :return:
    """
    data, truth = get_data_from_file(data_file, index, patch_shape=patch_shape)

    augment = augment_flipud or augment_fliplr or augment_elastic or augment_rotation or augment_shift or augment_shear or augment_zoom
    if augment:
        data_list = list()
        for i in range(data.shape[0]):
            data_list.append(data[i, :, :, :])
        data_list.append(truth[:, :, :])
        data_list = augment_data_new(data=data_list, augment_flipud=augment_flipud, augment_fliplr=augment_fliplr,
                                     augment_elastic=augment_elastic, augment_rotation=augment_rotation,
                                     augment_shift=augment_shift, augment_shear=augment_shear,
                                     augment_zoom=augment_zoom)
        for i in range(data.shape[0]):
            data[i, :, :, :] = data_list[i]
        truth[:, :, :] = data_list[-1]
    truth = truth[np.newaxis]
    # if not skip_blank or np.any(truth != 0):
    x_list.append(data)
    y_list.append(truth)


def add_data(x_list, y_list, data_file, index, augment=False, augment_flip=False, augment_distortion_factor=0.25,
             patch_shape=False, skip_blank=True, permute=False):
    """
    Adds data from the data file to the given lists of feature and target data
    :param skip_blank: Data will not be added if the truth vector is all zeros (default is True).
    :param patch_shape: Shape of the patch to add to the data lists. If None, the whole image will be added.
    :param x_list: list of data to which data from the data_file will be appended.
    :param y_list: list of data to which the target data from the data_file will be appended.
    :param data_file: hdf5 data file.
    :param index: index of the data file from which to extract the data.
    :param augment: if True, data will be augmented according to the other augmentation parameters (augment_flip and
    augment_distortion_factor)
    :param augment_flip: if True and augment is True, then the data will be randomly flipped along the x, y and z axis
    :param augment_distortion_factor: if augment is True, this determines the standard deviation from the original
    that the data will be distorted (in a stretching or shrinking fashion). Set to None, False, or 0 to prevent the
    augmentation from distorting the data in this way.
    :param permute: will randomly permute the data (data must be 3D cube)
    :return:
    """
    data, truth = get_data_from_file(data_file, index, patch_shape=patch_shape)
    if augment:
        if patch_shape is not None:
            affine = data_file.root.affine[index[0]]
        else:
            affine = data_file.root.affine[index]
        data, truth = augment_data(
            data, truth, affine, flip=augment_flip, scale_deviation=augment_distortion_factor)

    if permute:
        if data.shape[-3] != data.shape[-2] or data.shape[-2] != data.shape[-1]:
            raise ValueError("To utilize permutations, data array must be in 3D cube shape with all dimensions having "
                             "the same length.")
        data, truth = random_permutation_x_y(data, truth[np.newaxis])
    else:
        truth = truth[np.newaxis]

    if not skip_blank or np.any(truth != 0):
        x_list.append(data)
        y_list.append(truth)