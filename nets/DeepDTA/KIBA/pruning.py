import keras
import tensorflow as tf
from keras.datasets import mnist
from keras.preprocessing.image import ImageDataGenerator
from keras import optimizers
import numpy as np
import sys
from compressionNN import pruning
import pickle
import os
import keras.backend as K
from keras.utils import np_utils
from datahelper_noflag import *

SEED = 1

exec(open("../../GPU.py").read())

from numpy.random import seed
seed(SEED)
tf.random.set_seed(SEED)


def prepare_interaction_pairs(XD, XT,  Y, rows, cols):
    drugs = []
    targets = []
    targetscls = []
    affinity=[]

    for pair_ind in range(len(rows)):
        drug = XD[rows[pair_ind]]
        drugs.append(drug)

        target=XT[cols[pair_ind]]
        targets.append(target)

        affinity.append(Y[rows[pair_ind],cols[pair_ind]])

    drug_data = np.stack(drugs)
    target_data = np.stack(targets)

    return drug_data,target_data,  affinity

def find_index_first_dense(list_weights):
    i = 2
    for w in list_weights[2:]:
        if len(w.shape)==2:
            return i
        i += 1

max_seq_len = 1000
max_smi_len = 100

MODEL ='deepDTA_kiba.h5'

# data loading
dataset_path = 'kiba/'
problem_type = 1
dataset = DataSet( fpath = dataset_path, ### BUNU ARGS DA GUNCELLE
                      setting_no = problem_type, ##BUNU ARGS A EKLE
                      seqlen = max_seq_len,
                      smilen = max_smi_len,
                      need_shuffle = False )

charseqset_size = dataset.charseqset_size
charsmiset_size = dataset.charsmiset_size

XD, XT, Y = dataset.parse_data(dataset_path, 0)

XD = np.asarray(XD)
XT = np.asarray(XT)
Y = np.asarray(Y)

drugcount = XD.shape[0]
print(drugcount)
targetcount = XT.shape[0]
print(targetcount)

test_set, outer_train_sets = dataset.read_sets(dataset_path, problem_type)

flat_list = [item for sublist in outer_train_sets for item in sublist]

label_row_inds, label_col_inds = np.where(np.isnan(Y)==False)
trrows = label_row_inds[flat_list]
trcol = label_col_inds[flat_list]
drug, targ, aff = prepare_interaction_pairs(XD, XT,  Y, trrows, trcol)
trrows = label_row_inds[test_set]
trcol = label_col_inds[test_set]
drug_test, targ_test, aff_test = prepare_interaction_pairs(XD, XT,  Y, trrows, trcol)

batch_size = 128
input_set = tf.data.Dataset.from_tensor_slices((np.array(drug), np.array(targ)))
output_set = tf.data.Dataset.from_tensor_slices((np.array(aff)))
dataset = tf.data.Dataset.zip((input_set, output_set))
dataset = dataset.batch(batch_size)

x_train=[np.array(drug), np.array(targ)]
y_train=np.array(aff)
x_test=[np.array(drug_test), np.array(targ_test)]
y_test=np.array(aff_test)

full_cmd_arguments = sys.argv

argument_list = full_cmd_arguments[1:]

b = True if int(argument_list[0])==1 else False
if len(argument_list)==2:
    p = int(argument_list[1])
else:
    p = [int(argument_list[i]) for i in range (1,len(argument_list))]

div = 2

model = tf.keras.models.load_model(MODEL)

train_weights = model.get_weights()

index = find_index_first_dense(train_weights)

print(index)

pr_model = pruning.Pruning_NN(model=model, perc_prun_for_dense=p, index_first_dense=index, apply_compression_bias=b, div=div)

pre_pruning_train = pr_model.model.evaluate(x_train, y_train)
pre_pruning_test = pr_model.model.evaluate(x_test, y_test)

print("Accuracy prepruning test: ", pre_pruning_test)

pr_model.apply_pruning()
pr_model.set_loss(tf.keras.losses.MeanSquaredError())
pr_model.set_optimizer(tf.keras.optimizers.Adam(learning_rate=0.0003))



post_pruning_train = pr_model.model.evaluate(x_train, y_train)
post_pruning_test = pr_model.model.evaluate(x_test, y_test)

print("Accuracy postpruning train: ", post_pruning_train)
print("Accuracy postpruning test: ", post_pruning_test)


pr_model.train_pr_deepdta(epochs=100, dataset=dataset, X_train=x_train, y_train=y_train, X_test=x_test, y_test=y_test, step_per_epoch = 10000000, patience=0)

TRAIN_RES = ([pre_pruning_train] + [post_pruning_train] + pr_model.acc_train)
TEST_RES = ([pre_pruning_test] + [post_pruning_test] + pr_model.acc_test)


with open("deepdta_kiba_pruning.txt", "a+") as tex:
    tex.write("{} pruning {} -->\n {}\n , {}\n\n".format(b, p, TRAIN_RES, TEST_RES))

DIR="pruning"
TO_SAVE = "{}-{}".format(p,round(TEST_RES[-1],5))
if not os.path.isdir(DIR):
    os.mkdir(DIR)


pruned_weights = pr_model.get_pruned_weights()

with open(DIR+"/"+TO_SAVE+".h5", "wb") as file:
    pickle.dump(pruned_weights, file)
