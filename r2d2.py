""" Code for the MAML algorithm and network definitions. """
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

class R2D2:
    def __init__(self, dim_input=1, dim_output=1, test_num_updates=5):
        #tf.reset_default_graph()
        
        """ must call construct_model() after initializing MAML! """
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
                self.dim_hidden = FLAGS.num_filters
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

            def task_metalearn(inp, reuse=True):
                """ Perform gradient descent for one task in the meta-batch. """
                inputa, inputb, labela, labelb = inp
                task_outputbs, task_lossesb = [], []

                if self.classification:
                    task_accuraciesb = []
                
                task_outputa = self.forward(inputa, weights, reuse=reuse)  # only reuse on the first iter
                task_lossa = self.loss_func(task_outputa, labela)
                
                ## Pass through CNN
                x = self.forward_conv_CNN(inputa, weights, reuse=True)                
                
                ## Linear Regression with Woodbury Identity
                # using training set (a) to determine new weights for linear regressor
                xT = tf.transpose(x)
                xxT = tf.matmul(x,xT)
                
                # Calculate new LINEAR REGRESSION weights on train set, using the Woodbury identity
                fast_weights = dict(zip(weights.keys(), [weights[key] for key in weights.keys()]))
                fast_weights['stop_w5'] = tf.stop_gradient(tf.matmul(tf.matmul(xT,tf.linalg.inv(xxT + weights['lr_lambda'] * tf.eye(tf.shape(xxT)[0],tf.shape(xxT)[1]))),labela))
                
                # MAML line 8: calculate output/loss on test set (b), internally does LR conversion with scale alpha and bias beta
                output = self.forward(inputb, fast_weights, reuse=True)
                task_outputbs.append(output)
                task_lossesb.append(self.loss_func(output, labelb))
                
                # NO (further) INNER STEPS REQUIRED FOR LINEAR REGRESSION
                """
                for j in range(num_updates - 1):
                    loss = self.loss_func(self.forward(inputa, fast_weights, reuse=True), labela)
                    
                    # MAML line 5: evaluate grads on train set (a)
                    grads = tf.gradients(loss, list(fast_weights.values()))
                    if FLAGS.stop_grad:
                        grads = [tf.stop_gradient(grad) for grad in grads]
                    gradients = dict(zip(fast_weights.keys(), grads))
                    
                    # MAML line 6: compute updates (adapted parameters)
                    fast_weights = dict(zip(fast_weights.keys(), [fast_weights[key] - self.update_lr*gradients[key] for key in fast_weights.keys()]))
                    
                    # MAML line 8: calculate output/loss on test set (b)
                    output = self.forward(inputb, fast_weights, reuse=True)
                    task_outputbs.append(output)
                    task_lossesb.append(self.loss_func(output, labelb))
                """
                task_output = [task_outputa, task_outputbs, task_lossa, task_lossesb]

                if self.classification:
                    task_accuracya = tf.contrib.metrics.accuracy(tf.argmax(tf.nn.softmax(task_outputa), 1), tf.argmax(labela, 1))
                    for j in range(num_updates):
                        task_accuraciesb.append(tf.contrib.metrics.accuracy(tf.argmax(tf.nn.softmax(task_outputbs[j]), 1), tf.argmax(labelb, 1)))
                    task_output.extend([task_accuracya, task_accuraciesb])

                return task_output

            if FLAGS.norm is not 'None': # to initialize batch norm variables
                # to initialize the batch norm vars, might want to combine this, and not run idx 0 twice.
                unused = task_metalearn((self.inputa[0], self.inputb[0], self.labela[0], self.labelb[0]), False)

            out_dtype = [tf.float32, [tf.float32]*num_updates, tf.float32, [tf.float32]*num_updates]
            if self.classification: # accuracies are also stored
                out_dtype.extend([tf.float32, [tf.float32]*num_updates])
            # THE REAL LEARNING CONSTRUCTION OCCURS HERE
            # IMPORTANT: executes in parallel for ALL TASKS in batch I guess? The inputs are formatted in a special way to contain multiple tasks?
            result = tf.map_fn(task_metalearn, elems=(self.inputa, self.inputb, self.labela, self.labelb), dtype=out_dtype, parallel_iterations=FLAGS.meta_batch_size)
            if self.classification:
                outputas, outputbs, lossesa, lossesb, accuraciesa, accuraciesb = result
            else:
                outputas, outputbs, lossesa, lossesb  = result

        ## Performance & Optimization
        if 'train' in prefix:
            self.total_loss1 = total_loss1 = tf.reduce_sum(lossesa) / tf.to_float(FLAGS.meta_batch_size)
            self.total_losses2 = total_losses2 = [tf.reduce_sum(lossesb[j]) / tf.to_float(FLAGS.meta_batch_size) for j in range(num_updates)]
            # after the map_fn
            self.outputas, self.outputbs = outputas, outputbs
            #self.labelas, self.labelbs = outputas, outputbs
            if self.classification:
                self.total_accuracy1 = total_accuracy1 = tf.reduce_sum(accuraciesa) / tf.to_float(FLAGS.meta_batch_size)
                self.total_accuracies2 = total_accuracies2 = [tf.reduce_sum(accuraciesb[j]) / tf.to_float(FLAGS.meta_batch_size) for j in range(num_updates)]
            self.pretrain_op = tf.train.AdamOptimizer(self.meta_lr).minimize(total_loss1)

            if FLAGS.metatrain_iterations > 0: # FLAGS.metatrain_iterations = how many times to execute
                # This is the meta optimizer
                optimizer = tf.train.AdamOptimizer(self.meta_lr)
                
                # Compute gradients after num_updates
                self.gvs = gvs = optimizer.compute_gradients(self.total_losses2[FLAGS.num_updates-1])
                
                #grads = tf.gradients(loss, list(fast_weights.values()))
                #grads = [tf.stop_gradient(grad) for grad in gvs]
                
                # Gradients are clipped by [-10,10] to avoid explosion?
                if FLAGS.datasource == 'miniimagenet' or FLAGS.datasource == 'cifarfs':
                    gvs = [(tf.clip_by_value(grad, -10, 10), var) for grad, var in gvs if grad is not None]
                    
                # update parameters
                self.metatrain_op = optimizer.apply_gradients(gvs)
        else:
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

    ### Network construction functions
    ## CNN
    # initialize and return weights for CNN
    def construct_conv_weights(self):
        weights = {}

        dtype = tf.float32
        conv_initializer =  tf.contrib.layers.xavier_initializer_conv2d(dtype=dtype)
        fc_initializer =  tf.contrib.layers.xavier_initializer(dtype=dtype)
        k = 3

        # CNN weights
        weights['conv1'] = tf.get_variable('conv1', [k, k, self.channels, self.dim_hidden], initializer=conv_initializer, dtype=dtype)
        weights['b1'] = tf.Variable(tf.zeros([self.dim_hidden]))
        weights['conv2'] = tf.get_variable('conv2', [k, k, self.dim_hidden, self.dim_hidden], initializer=conv_initializer, dtype=dtype)
        weights['b2'] = tf.Variable(tf.zeros([self.dim_hidden]))
        weights['conv3'] = tf.get_variable('conv3', [k, k, self.dim_hidden, self.dim_hidden], initializer=conv_initializer, dtype=dtype)
        weights['b3'] = tf.Variable(tf.zeros([self.dim_hidden]))
        weights['conv4'] = tf.get_variable('conv4', [k, k, self.dim_hidden, self.dim_hidden], initializer=conv_initializer, dtype=dtype)
        weights['b4'] = tf.Variable(tf.zeros([self.dim_hidden]))
        
        # RR weights
        # assumes max pooling, flat_dim is concatenated flattened output of layer 3 and 4
        flat_dim = 640
        if FLAGS.datasource == 'miniimagenet': # 84x84 * (1/2 + 1/2/2/2)
            flat_dim = 4000
        else:# cifarfs 32x32 * (1/2 + 1/2/2/2) = 640
            flat_dim = 640 
        
        
        
        weights['stop_w5'] = tf.get_variable('stop_w5', [flat_dim, self.dim_output], initializer=fc_initializer)
        
        # hyper parameters of base learner, to be learnt in outer loop together with CNN parameters
        #weights['lr_lambda'] = tf.get_variable('lr_lambda', initializer=tf.constant(1., dtype=dtype), dtype=dtype)
        #weights['lr_alpha'] = tf.get_variable('lr_alpha',initializer=tf.constant(1., dtype=dtype), dtype=dtype)
        #weights['lr_beta'] = tf.get_variable('lr_beta', initializer=tf.constant(1., dtype=dtype), dtype=dtype)
        
        weights['lr_lambda'] = tf.Variable(tf.zeros(1, dtype = dtype))
        weights['lr_alpha'] = tf.Variable(tf.zeros(1, dtype = dtype))
        weights['lr_beta'] = tf.Variable(tf.zeros(1, dtype = dtype))
        
        
        #weights['b5'] = tf.Variable(tf.zeros([self.dim_output]), name='b5')

        return weights

    # return output of input image, with weights given as argument!
    # This is only to be used in the meta-learning step, during base training the direct solution for LR is used!
    def forward_conv(self, inp, weights, reuse=False, scope=''):
        out = self.forward_conv_CNN(inp, weights, reuse=reuse, scope=scope)
        out = self.forward_conv_lr(out, weights, reuse=reuse, scope=scope)
        
        return out
    
    def forward_conv_CNN(self, inp, weights, reuse=False, scope=''):
        # reuse is for the normalization parameters.
        channels = self.channels
        inp = tf.reshape(inp, [-1, self.img_size, self.img_size, channels])

        hidden1 = conv_block(inp, weights['conv1'], weights['b1'], reuse, scope+'0')
        hidden2 = conv_block(hidden1, weights['conv2'], weights['b2'], reuse, scope+'1')
        hidden3 = conv_block(hidden2, weights['conv3'], weights['b3'], reuse, scope+'2')
        hidden4 = conv_block(hidden3, weights['conv4'], weights['b4'], reuse, scope+'3')
        
        # Flattening of blocks 3 and 4
        hidden3 = tf.reshape(hidden3, [-1, np.prod([int(dim) for dim in hidden3.get_shape()[1:]])])
        hidden4 = tf.reshape(hidden4, [-1, np.prod([int(dim) for dim in hidden4.get_shape()[1:]])])
        
        # Concatenate 
        flatconcat34 = tf.concat([hidden3, hidden4], axis=1) # keep batched (axis 0), concatenate columns (axis 1)
        
        return flatconcat34
        
    def forward_conv_lr(self, inp, weights, reuse=False, scope=''):
        W = tf.stop_gradient(weights['stop_w5']) # stop backpropagation to CNN weights through RR calculation
        return tf.multiply(weights['lr_alpha'],tf.matmul(inp, W)) + tf.multiply(weights['lr_beta'],tf.ones(shape=[inp.get_shape()[0], self.dim_output], dtype=tf.float32))

