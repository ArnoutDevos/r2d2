""" Code for the R2D2 algorithm and network definitions. """
from __future__ import print_function
import numpy as np
import sys
import tensorflow as tf
try:
    import special_grads
except KeyError as e:
    print('WARN: Cannot define MaxPoolGrad, likely already defined for this version of tensorflow: %s' % e,
          file=sys.stderr)

from tensorflow.python.platform import flags
from utils import mse, xent, conv_block, normalize

FLAGS = flags.FLAGS

class R2D2_paper:
    """This class implements the R2D2 algorithm as proposed in "Meta-learning with differentiable closed-form solvers"

    Attributes:
        dim_input:          An integer equal to the (flattened) input size
        dim_hidden:         A list of integers which contains the number of (output) channels in each layer
        dim_output:         An integer equal to the (flattened) output size
        img_size:           An integer equal to the length of one side of a square image
        
        classification:     A boolean representing whether a classification is being carried out or not
        construct_weights:  A function that constructs the weights for the model to be used
        forward:            A function that defines the TensorFlow structure for a forward pass, building on the weights from construct_weights
        loss_func:          Loss function to be used, xent = cross entropy for classification, mse = mean squared error for regression
        
        update_lr:          A float for the base learning learning rate
        meta_lr:            A float for the meta learning rate, is part of the TensorFlow graph and can thus be modified when feeding
        test_num_updates:   An integer equal to the amount of finetuning steps that should be taken during training and testing
        
        activation:         Activation function to be used in the neural layers
        dropout:            A float signifying the percentage of neurons to be dropped out
        channels:           An integer equal to the number of channels in the input (image)
    """
    def __init__(self, dim_input=1, dim_output=1, test_num_updates=5):
        """Inits an R2D2 model
        
        Most attributes for this class are determined based on the
        arguments passed through the FLAGS.
        
        Currently this class supports the following datasets:
        miniImagenet, CIFAR-FS
        
        After initialization the function construct_model() should
        always be called. This is required before the TensorFlow graph
        can be feeded with data and operations can be executed.
        
        Args:
            dim_input:          An integer equal to the (flattened) input size
            dim_output:         An integer equal to the (flattened) output size
            test_num_updates:   An integer equal to the amount of finetuning steps that should be taken during training and testing

        Raises:
            ValueError: The dataset specified is not recognized
        """
        self.dim_input = dim_input
        self.dim_output = dim_output
        self.update_lr = FLAGS.update_lr
        self.meta_lr = tf.placeholder_with_default(FLAGS.meta_lr, ())
        self.classification = False
        self.test_num_updates = test_num_updates
        if FLAGS.datasource == 'sinusoid':
            self.dim_hidden = [40, 40]
            self.loss_func = mse
            self.forward = self.forward_fc
            self.construct_weights = self.construct_fc_weights
        elif FLAGS.datasource == 'omniglot' or FLAGS.datasource == 'miniimagenet' or FLAGS.datasource == 'cifarfs':
            self.loss_func = xent
            self.classification = True
            
            if FLAGS.conv:
                self.dropout = 0.0
                if FLAGS.model == 'r2d2':
                    self.activation = lambda x: tf.nn.leaky_relu(x, alpha=0.1)
                    self.dim_hidden = [96, 192, 384, 512]
                    
                    if FLAGS.datasource == 'miniimagenet':
                        self.dropout = 0.1
                    elif FLAGS.datasource == 'cifarfs':
                        self.dropout = 0.4
                        
                elif FLAGS.model == 'maml':
                    self.activation = tf.nn.relu
                    self.dim_hidden = [32, 32, 32, 32]
                
                self.forward = self.forward_conv
                self.construct_weights = self.construct_conv_weights
                    
            else:
                self.dim_hidden = [256, 128, 64, 64]
                self.forward=self.forward_fc
                self.construct_weights = self.construct_fc_weights
            
            # Determine amount of channels to use
            if FLAGS.datasource == 'miniimagenet' or FLAGS.datasource == 'cifarfs':
                self.channels = 3
            else:
                self.channels = 1
            
            # Compute image width (=height)
            self.img_size = int(np.sqrt(self.dim_input/self.channels)) # dim input is length of totally flattened image
        else:
            raise ValueError('Unrecognized data source.')

    def construct_model(self, input_tensors=None, prefix='metatrain_'):
        """Constructs the TensorFlow graph, and defines operations
        
        This function contains the meta-learning model in TensorFlow,
        and its operation definitions. Refer to the paper for algorithm
        details.
        
        Args:
            input_tensors:      tensorflow queues with inputs for base-training (a), and inputs for meta-training (b). Not required.
            prefix:             string with values {'metatrain_','metaval_'} to a model for training or evaluation respectively
        """
        # This function constructs the model, and defines the ops. The ops are not called yet! That happens in session.run(...)
        
        # a: training data for inner gradient, b: test data for meta gradient
        if input_tensors is None:
            self.inputa = tf.placeholder(tf.float32)
            self.inputb = tf.placeholder(tf.float32)
            self.labela = tf.placeholder(tf.float32)
            self.labelb = tf.placeholder(tf.float32)
        else: # Directly couple input tensors from tf queue to object variables
            self.inputa = input_tensors['inputa']
            self.inputb = input_tensors['inputb']
            self.labela = input_tensors['labela']
            self.labelb = input_tensors['labelb']

        with tf.variable_scope('model', reuse=None) as training_scope:
            # Use a seed for reproducibility
            tf.set_random_seed(1)
            
            if 'weights' in dir(self):
                # weights were already initialized during some training, reuse those
                training_scope.reuse_variables()
                weights = self.weights
            else:
                # Define the weights
                # this is done when construct_model is called
                self.weights = weights = self.construct_weights()

            # outputbs[i] and lossesb[i] is the output and loss after i+1 gradient updates
            lossesa, outputas, lossesb, outputbs, labelas, labelbs = [], [], [], [], [], []
            accuraciesa, accuraciesb = [], []
            num_updates = max(self.test_num_updates, FLAGS.num_updates)
            outputbs = [[]]*num_updates
            lossesb = [[]]*num_updates
            accuraciesb = [[]]*num_updates

            def task_baselearn(inp, reuse=True):
                """ Finetune on one task in the meta-batch. """
                inputa, inputb, labela, labelb = inp
                task_outputbs, task_lossesb = [], []

                if self.classification:
                    task_accuraciesb = []
                
                task_outputa = self.forward(inputa, weights, reuse=reuse)  # only reuse on the first iter
                task_lossa = self.loss_func(task_outputa, labela)
                
                ## Pass through CNN
                x = self.forward_conv_CNN(inputa, weights, reuse=True)                
                
                # Linear Regression with Woodbury Identity using training set (a) to determine new weights for linear regressor
                xT = tf.transpose(x)
                xxT = tf.matmul(x,xT)
                fast_weights = dict(zip(weights.keys(), [weights[key] for key in weights.keys()])) # Copy current weights
                fast_weights['stop_w5'] = tf.matmul(tf.matmul(xT,tf.linalg.inv(xxT + weights['lr_lambda'] * tf.eye(tf.shape(xxT)[0],tf.shape(xxT)[1]))),labela)

                # for dropout
                if FLAGS.train:
                    is_training = True
                else:
                    is_training = False
                
                # MAML line 8: calculate output/loss on test set (b), internally does LR conversion with scale alpha and bias beta
                output = self.forward(inputb, fast_weights, reuse=True, is_training=True)
                task_outputbs.append(output)
                task_lossesb.append(self.loss_func(output, labelb))
                
                task_output = [task_outputa, task_outputbs, task_lossa, task_lossesb]
                
                # When classification, extend the output with accuracies
                if self.classification:
                    task_accuracya = tf.contrib.metrics.accuracy(tf.argmax(tf.nn.softmax(task_outputa), 1), tf.argmax(labela, 1))
                    for j in range(num_updates):
                        task_accuraciesb.append(tf.contrib.metrics.accuracy(tf.argmax(tf.nn.softmax(task_outputbs[j]), 1), tf.argmax(labelb, 1)))
                    task_output.extend([task_accuracya, task_accuraciesb])

                return task_output

            if FLAGS.norm is not 'None': # to initialize BatchNorm variables, run the base_learning step on task 0
                unused = task_baselearn((self.inputa[0], self.inputb[0], self.labela[0], self.labelb[0]), False)

            out_dtype = [tf.float32, [tf.float32]*num_updates, tf.float32, [tf.float32]*num_updates]
            if self.classification: # accuracies are also stored in the case of classification
                out_dtype.extend([tf.float32, [tf.float32]*num_updates])

            # Executes fine tuning for ALL TASKS in meta batch: the input queues are formatted in a way to contain multiple tasks
            result = tf.map_fn(task_baselearn, elems=(self.inputa, self.inputb, self.labela, self.labelb), dtype=out_dtype, parallel_iterations=FLAGS.meta_batch_size)
            if self.classification:
                outputas, outputbs, lossesa, lossesb, accuraciesa, accuraciesb = result
            else:
                outputas, outputbs, lossesa, lossesb  = result

        ## Performance & Optimization
        if 'train' in prefix:
            # in meta-training: execute full base learning and meta learning
            self.total_loss1 = total_loss1 = tf.reduce_sum(lossesa) / tf.to_float(FLAGS.meta_batch_size)
            self.total_losses2 = total_losses2 = [tf.reduce_sum(lossesb[j]) / tf.to_float(FLAGS.meta_batch_size) for j in range(num_updates)]
            self.outputas, self.outputbs = outputas, outputbs

            if self.classification:
                self.total_accuracy1 = total_accuracy1 = tf.reduce_sum(accuraciesa) / tf.to_float(FLAGS.meta_batch_size)
                self.total_accuracies2 = total_accuracies2 = [tf.reduce_sum(accuraciesb[j]) / tf.to_float(FLAGS.meta_batch_size) for j in range(num_updates)]
            self.pretrain_op = tf.train.AdamOptimizer(self.meta_lr).minimize(total_loss1)

            if FLAGS.metatrain_iterations > 0: # FLAGS.metatrain_iterations = how many times to execute
                # This is the meta optimizer
                optimizer = tf.train.AdamOptimizer(self.meta_lr)
                
                # Compute gradients after num_updates
                self.gvs = gvs = optimizer.compute_gradients(self.total_losses2[FLAGS.num_updates-1])
                
                # Gradients are clipped by [-10,10] to avoid gradient explosion
                if FLAGS.datasource == 'miniimagenet' or FLAGS.datasource == 'cifarfs':
                    gvs = [(tf.clip_by_value(grad, -10, 10), var) for grad, var in gvs if grad is not None]
                    
                # update parameters
                self.metatrain_op = optimizer.apply_gradients(gvs)
        else:
            # in meta-validation: execute only base learning (fine tuning) and validate
            self.metaval_total_loss1 = total_loss1 = tf.reduce_sum(lossesa) / tf.to_float(FLAGS.meta_batch_size)
            self.metaval_total_losses2 = total_losses2 = [tf.reduce_sum(lossesb[j]) / tf.to_float(FLAGS.meta_batch_size) for j in range(num_updates)]
            
            if self.classification:
                self.metaval_total_accuracy1 = total_accuracy1 = tf.reduce_sum(accuraciesa) / tf.to_float(FLAGS.meta_batch_size)
                self.metaval_total_accuracies2 = total_accuracies2 =[tf.reduce_sum(accuraciesb[j]) / tf.to_float(FLAGS.meta_batch_size) for j in range(num_updates)]
                
                # For diagnostic purposes
                self.test_accuraciesa = accuraciesa
                self.test_accuraciesb = [accuraciesb[j] for j in range(num_updates)]
                
                self.test_outputas = outputas
                self.test_outputbs = outputbs
                
                self.labelas = self.labela
                self.labelbs = self.labelb

        ## Summaries
        tf.summary.scalar(prefix+'Pre-update loss', total_loss1)
        if self.classification:
            tf.summary.scalar(prefix+'Pre-update accuracy', total_accuracy1)

        for j in range(num_updates):
            tf.summary.scalar(prefix+'Post-update loss, step ' + str(j+1), total_losses2[j])
            if self.classification:
                tf.summary.scalar(prefix+'Post-update accuracy, step ' + str(j+1), total_accuracies2[j])

    def construct_conv_weights(self):
        """ R2D2 model weights initialziation:
        4 conv blocks:
        - 3x3 convolutions
        - batch-normalization
        - 2x2 max pooling
        - leaky relu (factor 0.1)
        - filters: [96, 192, 384, 512]
        - dropout on layer 3 and 4
        """
        weights = {}

        dtype = tf.float32
        conv_initializer =  tf.contrib.layers.xavier_initializer_conv2d(dtype=dtype)
        fc_initializer =  tf.contrib.layers.xavier_initializer(dtype=dtype)
        k = 3

        # CNN weights
        weights['conv1'] = tf.get_variable('conv1', [k, k, self.channels, self.dim_hidden[0]], initializer=conv_initializer, dtype=dtype)
        weights['b1'] = tf.Variable(tf.zeros([self.dim_hidden[0]]))
        weights['conv2'] = tf.get_variable('conv2', [k, k, self.dim_hidden[0], self.dim_hidden[1]], initializer=conv_initializer, dtype=dtype)
        weights['b2'] = tf.Variable(tf.zeros([self.dim_hidden[1]]))
        weights['conv3'] = tf.get_variable('conv3', [k, k, self.dim_hidden[1], self.dim_hidden[2]], initializer=conv_initializer, dtype=dtype)
        weights['b3'] = tf.Variable(tf.zeros([self.dim_hidden[2]]))
        weights['conv4'] = tf.get_variable('conv4', [k, k, self.dim_hidden[2], self.dim_hidden[3]], initializer=conv_initializer, dtype=dtype)
        weights['b4'] = tf.Variable(tf.zeros([self.dim_hidden[3]]))
        
        # RR weights
        # assumes max pooling, flat_dim is concatenated flattened output of layer 3 and 4
        flat_dim = 51200
        if FLAGS.model == 'maml':
            if FLAGS.datasource == 'miniimagenet':
                flat_dim = 4000
            elif FLAGS.datasource == 'cifarfs':
                flat_dim = 640
        else:
            if FLAGS.datasource == 'miniimagenet':
                flat_dim = 51200
            elif FLAGS.datasource == 'cifarfs':
                flat_dim = 8192
        
        weights['stop_w5'] = tf.get_variable('stop_w5', [flat_dim, self.dim_output], initializer=fc_initializer)
        
        # hyperparameters of base learner, to be learnt in outer loop together with CNN parameters     
        weights['lr_lambda'] = tf.Variable(tf.zeros(1, dtype = dtype))
        weights['lr_alpha'] = tf.Variable(tf.zeros(1, dtype = dtype))
        weights['lr_beta'] = tf.Variable(tf.zeros(1, dtype = dtype))

        return weights

    def forward_conv(self, inp, weights, reuse=False, scope='', is_training=False):
        """R2D2 model forward specification
        
        This is only to be used in the meta-learning step, during base training the direct solution for LR is used.
        
        It consists of:
        - Feature extractor CNN part, concatenate flattened outputs of layer 3 and 4
        - Linear regression prediction on concatenated flattened outputs of layer 3 and 4 with scale and bias adjust for cross-entropy loss
        
        Args:
            inp:            
            weights:        Model weights to be used for forward prediction
            reuse:          A boolean which defines whether or not to reuse the batch normalization initialization
            scope:          TensorFlow Variable scope to be used
            is_training:    A boolean signifying whether we are training or not, relevant for dropout
            
        """
        out = self.forward_conv_CNN(inp, weights, reuse=reuse, scope=scope, is_training=is_training)
        out = self.forward_conv_lr(out, weights, reuse=reuse, scope=scope, is_training=is_training)
        
        return out
    
    def forward_conv_CNN(self, inp, weights, reuse=False, scope='', is_training=False):
        """ R2D2 model specification, CNN part:
        4 conv blocks:
        - 3x3 convolutions
        - batch-normalization
        - 2x2 max pooling
        - leaky relu (factor 0.1)
        - filters: [96, 192, 384, 512]
        - dropout on layer 3 and 4
        - concatenate flattened outputs of layer 3 and 4
        
        Args:
            <see forward_conv()>
        """
        
        channels = self.channels
        inp = tf.reshape(inp, [-1, self.img_size, self.img_size, channels])

        hidden1 = conv_block(inp, weights['conv1'], weights['b1'], reuse, scope+'0', activation = self.activation)
        hidden2 = conv_block(hidden1, weights['conv2'], weights['b2'], reuse, scope+'1', activation = self.activation)
        hidden3 = conv_block(hidden2, weights['conv3'], weights['b3'], reuse, scope+'2', activation = self.activation)
        hidden3 = tf.layers.dropout(hidden3, rate=self.dropout, training=is_training)
        hidden4 = conv_block(hidden3, weights['conv4'], weights['b4'], reuse, scope+'3', activation = self.activation)
        hidden4 = tf.layers.dropout(hidden4, rate=self.dropout, training=is_training)
        
        # Flattening of blocks 3 and 4
        hidden3 = tf.reshape(hidden3, [-1, np.prod([int(dim) for dim in hidden3.get_shape()[1:]])])
        hidden4 = tf.reshape(hidden4, [-1, np.prod([int(dim) for dim in hidden4.get_shape()[1:]])])        
        
        # Concatenate 
        flatconcat34 = tf.concat([hidden3, hidden4], axis=1) # keep batched (axis 0), concatenate columns (axis 1)
        
        return flatconcat34
        
    def forward_conv_lr(self, inp, weights, reuse=False, scope='', is_training=False):
        """ R2D2 model specification, Linear Regression part:
        - Take in concatenated flattened outputs of layer 3 and 4
        - Perform linear regression prediction, with meta parameters scale alpha, and bias beta
        
        Args:
            <see forward_conv()>
        """
        
        W = weights['stop_w5']
        return tf.multiply(weights['lr_alpha'],tf.matmul(inp, W)) + tf.multiply(weights['lr_beta'],tf.ones(shape=[inp.get_shape()[0], self.dim_output], dtype=tf.float32))