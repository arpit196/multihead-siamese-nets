from layers.convolution import cnn_layers
from layers.losses import mse
from layers.losses import cross_entropy
from layers.similarity import manhattan_similarity
from models.base_model import BaseSiameseNet
from layers.recurrent import rnn_layer
from utils.config_helpers import parse_list
from layers.basics import dropout
import tensorflow as tf
import numpy as np

_conv_projection_size = 64
_attention_output_size = 100
_comparison_output_size = 64

class AttentionMatrixCnn(BaseSiameseNet):

    def __init__(self, max_sequence_len, vocabulary_size, main_cfg, model_cfg):
        BaseSiameseNet.__init__(self, max_sequence_len, vocabulary_size, main_cfg, model_cfg, mse)
          
        
    def _masked_softmax(self, values, lengths):
        with tf.name_scope('MaskedSoftmax'):
            mask = tf.expand_dims(tf.sequence_mask(lengths, tf.reduce_max(lengths), dtype=tf.float32), -2)
    
            inf_mask = (1 - mask) * -np.inf
            inf_mask = tf.where(tf.is_nan(inf_mask), tf.zeros_like(inf_mask), inf_mask)

            return tf.nn.softmax(tf.multiply(values, mask) + inf_mask)
        
    def _conv_pad(self, values):
        with tf.name_scope('convolutional_padding'):
            pad = tf.zeros([tf.shape(self.x1)[0], 1, self.embedding_size])
            return tf.concat([pad, values, pad], axis=1)
        

    def _attention_layer(self):
        with tf.name_scope('attention_layer'):
            e_X1 = tf.layers.dense(self._X1_conv, _attention_output_size, activation=tf.nn.relu, name='attention_nn')
            e_X2=tf.layers.dense(self._X2_conv, _attention_output_size, activation=tf.nn.relu,
                                 name='attention_nn',reuse=True)
            
            e = tf.matmul(e_X1, e_X2, transpose_b=True, name='e')
            
            self._beta = tf.matmul(self._masked_softmax(e, sequence_len), self._X2_conv, name='beta2')
            self._alpha = tf.matmul(self._masked_softmax(tf.transpose(e, [0,2,1]), sequence_len), self._X1_conv, name='alpha2')
            
    def siamese_layer(self, sequence_len, model_cfg):
        _conv_filter_size = 3
        #parse_list(model_cfg['PARAMS']['filter_sizes'])
        with tf.name_scope('convolutional_layer'):
            X1_conv_1 = tf.layers.conv1d(
                self._conv_pad(self.embedded_x1),
                _conv_projection_size,
                _conv_filter_size,
                padding='valid',
                use_bias=False,
                name='conv_1',
            )
            
            X2_conv_1 = tf.layers.conv1d(
                self._conv_pad(self.embedded_x2),
                _conv_projection_size,
                _conv_filter_size,
                padding='valid',
                use_bias=False,
                name='conv_1',
                reuse=True
            )
            
            X1_conv_1 = tf.layers.dropout(X1_conv_1, rate=self.dropout, training=self.is_training)
            X2_conv_1 = tf.layers.dropout(X2_conv_1, rate=self.dropout, training=self.is_training)
            
            X1_conv_2 = tf.layers.conv1d(
                self._conv_pad(X1_conv_1),
                _conv_projection_size,
                _conv_filter_size,
                padding='valid',
                use_bias=False,
                name='conv_2',
            )
            
            X2_conv_2 = tf.layers.conv1d(
                self._conv_pad(X2_conv_1),
                _conv_projection_size,
                _conv_filter_size,
                padding='valid',
                use_bias=False,
                name='conv_2',
                reuse=True
            )
            
            self._X1_conv = tf.layers.dropout(X1_conv_2, rate=self.dropout, training=self.is_training)
            self._X2_conv = tf.layers.dropout(X2_conv_2, rate=self.dropout, training=self.is_training)
            
        with tf.name_scope('attention_layer'):
            e_X1 = tf.layers.dense(self._X1_conv, _attention_output_size, activation=tf.nn.relu, name='attention_nn')
            
            e_X2 = tf.layers.dense(self._X2_conv, _attention_output_size, activation=tf.nn.relu, name='attention_nn', reuse=True)
            
            e = tf.matmul(e_X1, e_X2, transpose_b=True, name='e')
            
            self._beta = tf.matmul(self._masked_softmax(e, sequence_len), self._X2_conv, name='beta2')
            self._alpha = tf.matmul(self._masked_softmax(tf.transpose(e, [0,2,1]), sequence_len), self._X1_conv, name='alpha2')
            
        with tf.name_scope('self_attention1'):
            e_X1 = tf.layers.dense(self._X1_conv, _attention_output_size, activation=tf.nn.relu, name='attention_nn1')
            
            e_X2 = tf.layers.dense(self._X1_conv, _attention_output_size, activation=tf.nn.relu, name='attention_nn1', reuse=True)
            
            e = tf.matmul(e_X1, e_X2, transpose_b=True, name='e')
            
            self._beta1 = tf.matmul(self._masked_softmax(e, sequence_len), self._X1_conv, name='beta2') 
            
        with tf.name_scope('self_attention2'):
            e_X1 = tf.layers.dense(self._X2_conv, _attention_output_size, activation=tf.nn.relu, name='attention_nn2')
            
            e_X2 = tf.layers.dense(self._X2_conv, _attention_output_size, activation=tf.nn.relu, name='attention_nn2', reuse=True)
            
            e = tf.matmul(e_X1, e_X2, transpose_b=True, name='e')
            
            self._alpha1 = tf.matmul(self._masked_softmax(e, sequence_len), self._X2_conv, name='beta2')
        W=tf.get_variable("W",shape=(78,64),dtype=tf.float32,initializer=tf.random_normal_initializer())
        W1=tf.get_variable("W1",shape=(78,64),dtype=tf.float32,initializer=tf.random_normal_initializer())
        with tf.name_scope('comparison_layer'):
            X1_comp = tf.layers.dense(
                tf.concat([self._X1_conv, self._beta ,tf.add(self._X1_conv,self._beta),tf.multiply(tf.multiply(self._X1_conv,W),self._beta)], 2),
                _comparison_output_size,
                activation=tf.nn.relu,
                name='comparison_nn'
            )
            X1_comp1 = tf.layers.dense(
                tf.concat([X1_comp, self._beta1, tf.add(X1_comp,self._beta1),tf.multiply(tf.multiply(X1_comp,W1),self._beta1)], 2),
                _comparison_output_size,
                activation=tf.nn.relu,
                name='comparison_nn1'
            )
            self._X1_comp = tf.multiply(
                tf.layers.dropout(X1_comp1, rate=self.dropout, training=self.is_training),
                tf.expand_dims(tf.sequence_mask(sequence_len, tf.reduce_max(sequence_len), dtype=tf.float32), -1)
            )
            
            X2_comp = tf.layers.dense(
                tf.concat([self._X2_conv, self._alpha, tf.add(self._X2_conv,self._alpha), tf.multiply(tf.multiply(self._X2_conv,W),self._alpha)], 2),
                _comparison_output_size,
                activation=tf.nn.relu,
                name='comparison_nn',
                reuse=True
            )
            X2_comp1 = tf.layers.dense(
                tf.concat([X2_comp, self._alpha1, tf.add(X2_comp,self._alpha1), tf.multiply(tf.multiply(X2_comp,W1),self._alpha1)], 2),
                _comparison_output_size,
                activation=tf.nn.relu,
                name='comparison_nn1',
                reuse=True
            )
                           
            self._X2_comp = tf.multiply(
                tf.layers.dropout(X2_comp1, rate=self.dropout, training=self.is_training),
                tf.expand_dims(tf.sequence_mask(sequence_len, tf.reduce_max(sequence_len), dtype=tf.float32), -1)
            )
            #outputs_sen1 = rnn_layer(self.embedded_x1, hidden_size=128, cell_type='GRU', bidirectional=True)
            #outputs_sen2 = rnn_layer(self.embedded_x2, hidden_size=128, cell_type='GRU', bidirectional=True, reuse=True)

            #out1 = tf.reduce_mean(outputs_sen1, axis=1)
            #out2 = tf.reduce_mean(outputs_sen2, axis=1)
            
            X1_agg = tf.reduce_sum(self._X1_comp, 1)
            X2_agg = tf.reduce_sum(self._X2_comp, 1)
            
            self._agg=tf.concat([X1_agg, X2_agg], 1)
            #self._agg1 = tf.concat([X1_agg, out1], 1)
            #self._agg2 = tf.concat([X2_agg, out2], 1)
            return manhattan_similarity(X1_agg,X2_agg)
