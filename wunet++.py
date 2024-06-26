import os
import io
import random
import nibabel
import numpy as np
import nibabel as nib
import tensorflow as tf
import matplotlib.pyplot as plt
import glob
from keras.utils import Sequence
from IPython.display import Image, display
from skimage.exposure import rescale_intensity
from skimage.segmentation import mark_boundaries
from keras.callbacks import ModelCheckpoint, EarlyStopping, TensorBoard
from keras.utils import normalize
from sklearn.model_selection import train_test_split
from keras.callbacks import Callback
from sklearn.model_selection import KFold
from keras.models import Model
from keras.layers import Input, Conv2D, MaxPooling2D, UpSampling2D, concatenate, Conv2DTranspose, BatchNormalization, Dropout, Lambda

def dice_coef(y_true, y_pred, smooth=1.):
    y_true_f = tf.cast(tf.keras.backend.flatten(y_true), tf.float64)
    y_pred_f = tf.cast(tf.keras.backend.flatten(y_pred), tf.float64)
    intersection = tf.keras.backend.sum(y_true_f * y_pred_f)
    return (2. * intersection + smooth) / (tf.keras.backend.sum(y_true_f) + tf.keras.backend.sum(y_pred_f) + smooth)

def tprf(y_true, y_prob, threshold):
    y_pred = (y_prob >= threshold)
   
    tp = np.sum((y_pred == 1) & (y_true == 1))
    fn = np.sum((y_pred == 0) & (y_true == 1))

    if (tp == 0):
        tpr = 0
    else:
        tpr = tp / (tp + fn)

    return tpr

def fprf(y_true, y_prob, threshold):
    y_pred = (y_prob >= threshold)

    fp = np.sum((y_pred == 1) & (y_true == 0))
    tn = np.sum((y_pred == 0) & (y_true == 0))
    
    if (fp == 0):
        fpr = 0
    else:
        fpr = fp / (fp + tn)

    return fpr

def conv_block(input_tensor, num_filters):
    x = Conv2D(num_filters, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same')(input_tensor)
    x = Dropout(0.1)(x)
    x = Conv2D(num_filters, (3, 3), activation='relu', kernel_initializer='he_normal', padding='same')(x)
    return x

def simple_unet_plus_model(IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS):
    inputs = Input((IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS))
    s = inputs

    # Contraction path (Encoder)
    c1 = conv_block(s, 16)
    p1 = MaxPooling2D((2, 2))(c1)
    c2 = conv_block(p1, 32)
    p2 = MaxPooling2D((2, 2))(c2)
    c3 = conv_block(p2, 64)
    p3 = MaxPooling2D((2, 2))(c3)
    c4 = conv_block(p3, 128)
    p4 = MaxPooling2D((2, 2))(c4)
    c5 = conv_block(p4, 256)

    # Expansive path with nested skip pathways (Decoder)
    u6 = Conv2DTranspose(128, (2, 2), strides=(2, 2), padding='same')(c5)
    u6 = concatenate([u6, c4])
    c6 = conv_block(u6, 128)

    u7 = Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same')(c6)
    u7 = concatenate([u7, c3, Conv2DTranspose(64, (2, 2), strides=(2, 2), padding='same')(c4)])
    c7 = conv_block(u7, 64)

    u8 = Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same')(c7)
    u8 = concatenate([u8, c2, Conv2DTranspose(32, (2, 2), strides=(2, 2), padding='same')(c3), Conv2DTranspose(32, (3, 3), strides=(4, 4), padding='same')(c4)])
    c8 = conv_block(u8, 32)

    u9 = Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same')(c8)
    u9 = concatenate([u9, c1, Conv2DTranspose(16, (2, 2), strides=(2, 2), padding='same')(c2), Conv2DTranspose(16, (3, 3), strides=(4, 4), padding='same')(c3), Conv2DTranspose(16, (4, 4), strides=(8, 8), padding='same')(c4)])
    c9 = conv_block(u9, 16)

    outputs = Conv2D(1, (1, 1), activation='sigmoid')(c9)

    model = Model(inputs=[inputs], outputs=[outputs])
    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=[dice_coef])
    model.summary()

    return model

image_directory = 'MRI/test_anatomical/'
mask_directory = 'MRI/test_liver_seg/'

image_dataset = []  
mask_dataset = []
sliced_image_dataset = []
sliced_mask_dataset = []
sliced_image_filenames = []

# SIZE = 128

images = os.listdir(image_directory)
for i, image_name in enumerate(images):    
    if (image_name.split('.')[1] == 'nii'):
        image = nib.load(image_directory + image_name)
        image = np.array(image.get_fdata())
        # image = resize(image, (SIZE, SIZE))
        image_dataset.append(np.array(image))
        sliced_image_filenames.append(os.path.splitext(image_name)[0])  # Extract filename without extension

masks = os.listdir(mask_directory)
for i, image_name in enumerate(masks):
    if (image_name.split('.')[1] == 'nii'):
        image = nib.load(mask_directory + image_name)
        image = np.array(image.get_fdata())
        # image = resize(image, (SIZE, SIZE))
        mask_dataset.append(np.array(image))

for i in range(len(image_dataset)):
    for j in range(image_dataset[i].shape[2]):
        sliced_image_dataset.append(image_dataset[i][:,:,j])

for i in range(len(mask_dataset)):
    for j in range(mask_dataset[i].shape[2]):
        if i == 16 and j == 25:
            continue
        else:
            sliced_mask_dataset.append(mask_dataset[i][:,:,j])

# Normalize and convert images
sliced_image_dataset = np.expand_dims(np.array(sliced_image_dataset), 3)
sliced_image_dataset = sliced_image_dataset.astype('float64')

# Convert masks and ensure they are in the correct format
sliced_mask_dataset = np.expand_dims(np.array(sliced_mask_dataset), 3)
sliced_mask_dataset = sliced_mask_dataset.astype('float64')

# Sanity check, view a few images
# image_number = random.randint(0, len(X_train))
# plt.figure(figsize=(12, 6))
# plt.subplot(121)
# plt.imshow(X_train[image_number], cmap='gray')
# plt.subplot(122)
# plt.imshow(y_train[image_number], cmap='gray')
# plt.show()

dice_scores = []
TPRs = []
FPRs = []

IMG_HEIGHT = sliced_image_dataset.shape[1]
IMG_WIDTH  = sliced_image_dataset.shape[2]
IMG_CHANNELS = sliced_image_dataset.shape[3]

def get_model():
    return simple_unet_plus_model(IMG_HEIGHT, IMG_WIDTH, IMG_CHANNELS)

model = get_model()

n_splits = 5

kf = KFold(n_splits=n_splits, shuffle=True, random_state=0)

histories = []

# Iterate over each fold

for i, (train_index, test_index) in enumerate(kf.split(sliced_image_dataset, sliced_mask_dataset)):
    X_train, X_test = sliced_image_dataset[train_index], sliced_image_dataset[test_index]
    y_train, y_test = sliced_mask_dataset[train_index], sliced_mask_dataset[test_index]
    sliced_image_filenames = [os.path.splitext(image_name)[0] for image_name in images if image_name.endswith('.nii')]


    checkpoint = ModelCheckpoint(f'kunetplus/best_model{i}.keras', monitor='val_loss', save_best_only=True)

    history = model.fit(X_train, y_train,
                        batch_size=16,
                        verbose=1,
                        epochs=5,
                        validation_data=(X_test, y_test),
                        shuffle=False,
                        callbacks=[checkpoint])

    histories.append(history)

    plt.figure(figsize=(15,5))
    plt.subplot(1,2,1)
    plt.plot(history.history['loss'], color='r')
    plt.plot(history.history['val_loss'])
    plt.ylabel('Losses')
    plt.xlabel('Epoch')
    plt.legend(['Train', 'Val.'], loc='upper right')
    plt.subplot(1,2,2)
    plt.plot(history.history['dice_coef'], color='r')
    plt.plot(history.history['val_dice_coef'])
    plt.ylabel('dice_coef')
    plt.xlabel('Epoch')
    plt.tight_layout()
    plt.savefig(f'kunetplus/process{i}.png')
    plt.close()

    max_dice_coef = max(history.history['dice_coef'])
    max_val_dice_coef = max(history.history['val_dice_coef'])

    with open("kunetplus/output.txt", "a") as f:
        print("max dice: ", max_dice_coef, file=f)
        print("max val dice: ", max_val_dice_coef, file=f)

    model.load_weights(f'kunetplus/best_model{i}.keras')

    for filename in sliced_image_filenames:
        test_patient_idx = random.randint(0, len(X_test) - 1)  # Define test_patient_idx inside the loop
        test_patient_slices = []
        for slice_idx in range(-5, 6):
            test_slice_idx = min(max(test_patient_idx + slice_idx, 0), len(X_test) - 1)
            test_patient_slices.append(test_slice_idx)
        
        for z in test_patient_slices:
            test_img = X_test[z]
            ground_truth = y_test[z]
            test_img_norm = test_img[:,:,0][:,:,None]
            test_img_input = np.expand_dims(test_img_norm, 0)
            prediction = (model.predict(test_img_input)[0,:,:,0] > 0.5).astype(np.uint8)

            original_image_normalized = ground_truth.astype(float) / np.max(ground_truth)
            colored_mask = plt.get_cmap('jet')(prediction / np.max(prediction))
            alpha = 0.5 
            colored_mask[..., 3] = np.where(prediction > 0, alpha, 0)

            dice_score = dice_coef(ground_truth, prediction)
            dice_scores.append(dice_score)

            tpr = tprf(ground_truth, prediction, 0.5)
            TPRs.append(tpr)

            fpr = fprf(ground_truth, prediction, 0.5)
            FPRs.append(fpr)

            with open("kunetplus/output.txt", "a") as f:
                print("tpr: ", tpr, file=f)
                print("fpr: ", fpr, file=f)

            plt.figure(figsize=(16, 8))
            plt.subplot(141)
            plt.title('Testing Image')
            plt.imshow(test_img[:,:,0], cmap='gray')
            plt.subplot(142)
            plt.title('Testing Label')
            plt.imshow(ground_truth[:,:,0], cmap='gray')
            plt.subplot(143)
            plt.title('Prediction on test image')
            plt.imshow(prediction, cmap='gray')
            plt.subplot(144)
            plt.title("Overlayed Images")
            plt.imshow(original_image_normalized, cmap='gray')
            plt.imshow(colored_mask, cmap='jet')
            plt.savefig(f'kunetplus/predict/fold{i}_{filename}_slice{z}.png')
            plt.close()

average_dice_coef = np.mean(dice_scores)
average_tpr = np.mean(TPRs)
average_fpr = np.mean(FPRs)

with open("kunetplus/output.txt", "a") as f:
    print('average prediction dice score', file=f)
    print(average_dice_coef, file=f)
    print('average prediction tpr', file=f)
    print(average_tpr, file=f)
    print('average prediction fpr', file=f)
    print(average_fpr, file=f)
