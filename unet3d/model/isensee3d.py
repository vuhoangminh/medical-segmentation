from functools import partial

from keras.layers import Input, LeakyReLU, Add, UpSampling3D, Activation, SpatialDropout3D, Conv3D
from keras.layers.merge import concatenate
from keras.engine import Model
from keras.optimizers import Adam
from keras.utils import multi_gpu_model

from unet3d.model.blocks import create_convolution_block3d
from unet3d.metrics import weighted_dice_coefficient_loss, tversky_loss, minh_dice_coef_loss, minh_dice_coef_metric
from unet3d.utils.model_utils import compile_model

create_convolution_block3d = partial(
    create_convolution_block3d, activation=LeakyReLU, instance_normalization=True)


def isensee2017_model(input_shape=(4, 128, 128, 128), n_base_filters=16, depth=5, dropout_rate=0.3,
                      n_segmentation_levels=3, n_labels=4, optimizer=Adam, initial_learning_rate=5e-4,
                      loss_function="weighted", activation_name="sigmoid", metrics=minh_dice_coef_metric,
                      labels=[1, 2, 4]):
    """
    This function builds a model proposed by Isensee et al. for the BRATS 2017 challenge:
    https://www.cbica.upenn.edu/sbia/Spyridon.Bakas/MICCAI_BraTS/MICCAI_BraTS_2017_proceedings_shortPapers.pdf

    This network is highly similar to the model proposed by Kayalibay et al. "CNN-based Segmentation of Medical
    Imaging Data", 2017: https://arxiv.org/pdf/1701.03056.pdf


    :param input_shape:
    :param n_base_filters:
    :param depth:
    :param dropout_rate:
    :param n_segmentation_levels:
    :param n_labels:
    :param optimizer:
    :param initial_learning_rate:
    :param loss_function:
    :param activation_name:
    :return:
    """
    inputs = Input(input_shape)

    current_layer = inputs
    level_output_layers = list()
    level_filters = list()
    for level_number in range(depth):
        n_level_filters = (2**level_number) * n_base_filters
        level_filters.append(n_level_filters)

        if current_layer is inputs:
            in_conv = create_convolution_block3d(
                current_layer, n_level_filters)
        else:
            in_conv = create_convolution_block3d(
                current_layer, n_level_filters, strides=(2, 2, 2))

        context_output_layer = create_context_module3d(
            in_conv, n_level_filters, dropout_rate=dropout_rate)

        summation_layer = Add()([in_conv, context_output_layer])
        level_output_layers.append(summation_layer)
        current_layer = summation_layer

    segmentation_layers = list()
    for level_number in range(depth - 2, -1, -1):
        up_sampling = create_up_sampling_module3d(
            current_layer, level_filters[level_number])
        concatenation_layer = concatenate(
            [level_output_layers[level_number], up_sampling], axis=1)
        localization_output = create_localization_module3d(
            concatenation_layer, level_filters[level_number])
        current_layer = localization_output
        if level_number < n_segmentation_levels:
            segmentation_layers.insert(
                0, Conv3D(n_labels, (1, 1, 1))(current_layer))

    output_layer = None
    for level_number in reversed(range(n_segmentation_levels)):
        segmentation_layer = segmentation_layers[level_number]
        if output_layer is None:
            output_layer = segmentation_layer
        else:
            output_layer = Add()([output_layer, segmentation_layer])

        if level_number > 0:
            output_layer = UpSampling3D(size=(2, 2, 2))(output_layer)

    activation_block = Activation(activation_name)(output_layer)

    model = Model(inputs=inputs, outputs=activation_block)

    return compile_model(model, loss_function=loss_function,
                         metrics=metrics,
                         labels=labels,
                         initial_learning_rate=initial_learning_rate)


def create_localization_module3d(input_layer, n_filters, weight_decay=0):
    convolution1 = create_convolution_block3d(
        input_layer, n_filters, weight_decay=0)
    convolution2 = create_convolution_block3d(
        convolution1, n_filters, kernel=(1, 1, 1), weight_decay=0)
    return convolution2


def create_up_sampling_module3d(input_layer, n_filters, size=(2, 2, 2), weight_decay=0):
    up_sample = UpSampling3D(size=size)(input_layer)
    convolution = create_convolution_block3d(
        up_sample, n_filters, weight_decay=weight_decay)
    return convolution


def create_context_module3d(input_layer, n_level_filters, dropout_rate=0.3,
                            data_format="channels_first",
                            weight_decay=0):
    convolution1 = create_convolution_block3d(
        input_layer=input_layer, n_filters=n_level_filters, weight_decay=weight_decay)
    dropout = SpatialDropout3D(
        rate=dropout_rate, data_format=data_format)(convolution1)
    convolution2 = create_convolution_block3d(
        input_layer=dropout, n_filters=n_level_filters, weight_decay=weight_decay)
    return convolution2
