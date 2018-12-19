""" Utility functions. """
import numpy as np
import os
import random
import tensorflow as tf

from tensorflow.contrib.layers.python import layers as tf_layers
from tensorflow.python.platform import flags

FLAGS = flags.FLAGS

## Image helper
def get_images(paths, labels, nb_samples=None, shuffle=True):
    """ Fetch list of tuples of image class and filepath
    
    Args:
        paths:          List of strings of image filepaths
        labels:         List of integers of image classes
        nb_samples:     An integer equal to the amount of samples wanted
        shuffle:        A boolean to signify whether a random shuffle is wanted or not

    returns:
        list of tuples (class, filepath)
    """
    if nb_samples is not None:
        sampler = lambda x: random.sample(x, nb_samples)
    else:
        sampler = lambda x: x
    images = [(i, os.path.join(path, image)) \
        for i, path in zip(labels, paths) \
        for image in sampler(os.listdir(path))]
    if shuffle:
        random.shuffle(images)
    return images

## Network helpers
def conv_block(inp, cweight, bweight, reuse, scope, activation=tf.nn.relu, max_pool_pad='VALID', residual=False):
    """ Construct a TensorFlow convolutional block
    
    Pipeline: conv, batch norm, nonlinearity, and max pool
    
    Args:
        inp:            Tensor input of convolutional block
        cweight:        Channel weights (filters)
        bweight:        Biases to be added to each filter
        reuse:          A boolean to reuse the batchnorm variables or not
        scope:          TensorFlow scope in which the variables reside
        activation:     TensorFlow nonlinearity function, default tf.nn.relu
        max_pool_pad:   Max pool padding setting, default = 'VALID'
        residual:       NOT USED

    returns:
        tensor output of convolutional block input
    """
    stride, no_stride = [1,2,2,1], [1,1,1,1]

    if FLAGS.max_pool:
        conv_output = tf.nn.conv2d(inp, cweight, no_stride, 'SAME') + bweight
    else:
        conv_output = tf.nn.conv2d(inp, cweight, stride, 'SAME') + bweight
    normed = normalize(conv_output, activation, reuse, scope)
    if FLAGS.max_pool:
        normed = tf.nn.max_pool(normed, stride, stride, max_pool_pad)
    return normed

def normalize(inp, activation, reuse, scope):
    """ Batch Normalization
    
    Args:
        inp:            Tensor input of convolutional block
        reuse:          A boolean to reuse the batchnorm variables or not
        scope:          TensorFlow scope in which the variables reside
        activation:     TensorFlow nonlinearity function, default tf.nn.relu

    returns:
        tensor output of BatchNorm input
    """
    if FLAGS.norm == 'batch_norm':
        return tf_layers.batch_norm(inp, activation_fn=activation, reuse=reuse, scope=scope)
    elif FLAGS.norm == 'layer_norm':
        return tf_layers.layer_norm(inp, activation_fn=activation, reuse=reuse, scope=scope)
    elif FLAGS.norm == 'None':
        if activation is not None:
            return activation(inp)
        else:
            return inp

## Loss functions
def mse(pred, label):
    """ Calculates Mean Squared Error
    
    Args:
        pred:   Tensor of label predictions
        label:  Tensor of golden labels (True values)

    returns:
        Mean Squared Error of predictions and labels
    """
    pred = tf.reshape(pred, [-1])
    label = tf.reshape(label, [-1])
    return tf.reduce_mean(tf.square(pred-label))

def xent(pred, label):
    """ Calculates Cross Entropy Loss
    
    Args:
        pred:   Tensor of label predictions
        label:  Tensor of golden labels (True values)

    returns:
        Mean Squared Error of predictions and labels
    """
    # Note - with tf version <=0.12, this loss has incorrect 2nd derivatives
    return tf.nn.softmax_cross_entropy_with_logits(logits=pred, labels=label) / FLAGS.update_batch_size
