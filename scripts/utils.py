from keras.utils.visualize_util import plot
from keras.preprocessing.image import ImageDataGenerator
from keras import backend as K
from keras.models import load_model
import numpy as np
import h5py, pickle, cv2
from os.path import abspath, dirname
from os import listdir
import scipy as sp
from datetime import datetime
from shutil import copyfile
from PIL import Image, ImageEnhance, ImageFilter
from random import randint

ROOT = dirname(dirname(abspath(__file__)))
TEST_DIR = ROOT + '/test/'
VAL_DIR = ROOT + '/validation/'
channels, img_width, img_height = 3, 300, 300
mini_batch_sz = 16
ext = '.jpg'
lb, lbub, ublb, ub = 0.1, 0.4, 0.6, 0.9
zoom_width, zoom_height, step = 120, 120, 40

def logloss(actual, preds):
	epsilon = 1e-15
	ll = 0
	for act, pred in zip(actual, preds):
		pred = max(epsilon, pred)
		pred = min(1-epsilon, pred)
		ll += act*sp.log(pred) + (1-act)*sp.log(1-pred)
	return -ll / len(actual)

def to_PIL(image, tf):
	if not tf:
		return Image.fromarray(np.asarray(image.transpose(1, 2, 0), dtype=np.uint8))
	return Image.fromarray(image.astype(np.uint8))
	
def to_theano(image):
	return np.asarray(image, dtype='float32').transpose(2, 0 ,1)

def visualizer(model):
	plot(model, to_file=ROOT + '/vis.png', show_shapes=True)

def dog_probab(y):
	return [x[0] for x in y]

def doubtful(pred):
	return (pred > lb and pred < lbub) or (pred < ub and pred > ublb)

def read_image(file_path):
	return to_theano(Image.open(file_path).convert('RGB').resize((img_height, img_width)))

def write_image(image, file_path, tf=False):
	to_PIL(image, tf).save(file_path)

def show(image):
	to_PIL(image).show()

def rotate(image, degrees):
	return image.rotate(degrees)

def resize(arr, h, w):
	return to_theano(to_PIL(arr).resize((h,w)))

def crop(arr, x, y, size):
	W,H = arr.shape[1:]
	return to_theano(to_PIL(arr).crop((x,y,x + size, y + size)))

def resizeX(arr, size):
	X = np.ndarray(arr.shape[:2] + (size, size),dtype=np.float32)
	for i, x in enumerate(arr): X[i] = resize(x, size, size)
	return X

def cropX(arr, size, training=True, x=None, y=None):
	# if not training:
	# 	w = h = 400
	# 	x, y = randint(0, w - size), randint(0, h - size)
	X = np.ndarray(arr.shape[:2] + (size, size),dtype=np.float32)
	for i in xrange(len(arr)): X[i] = crop(arr[i], x, y, size)
	return X

def getXY(q, size, imsize=400):
	h = w = imsize
	x1, y1 = randint(0, min(imsize - size - 1, imsize/2)), randint(0, min(imsize - size - 1, imsize/2))
	if q == 0:
		# top left
		return x1, y1
	if q == 1:
		# top right
		return w - x1 - size, y1
	if q == 2:
		# bottom right
		return w - x1 - size, h - y1 - size
	if q == 3:
		# bottom left
		return x1, h - y1 - size

def getVariations(image):
	img = Image.fromarray(np.asarray(image.transpose(1, 2, 0), dtype=np.uint8))
	images = []
	for degree in xrange(0, 360, 90):
		tmp = img.copy()
		tmp = rotate(tmp, degree)
		for x in xrange(0, img_width, step):
			for y in xrange(0, img_height, step):
				temp = tmp.copy()
				images.append(to_theano(temp.crop((x, y, x + zoom_width, y + zoom_height)).resize((img_height, 
							img_width))))
	
	return np.asarray(images)

def standardized(gen):
	mean, stddev = pickle.load(open('meanSTDDEV'))
	while 1:
		X = gen.next()
		for i in xrange(len(X)):
			X[i] = (X[i] - mean) / stddev
		yield X

def prep_data(images, img_height1, img_width1, inception=False):
	batches = [images[i:min(len(images), i + mini_batch_sz)] 
				for i in xrange(0, len(images), mini_batch_sz)]
	for mini_batch in batches:
		data = np.ndarray((len(mini_batch), img_height1, img_width1, channels), 
							dtype=np.float32)
		for i, image_file in enumerate(mini_batch):
			data[i] = np.asarray(Image.open(image_file).convert('RGB').resize((img_height1, img_width1)), 
						dtype=np.float32)
			if inception:
				data[i] = np.divide(data[i], 255.0)
				data[i] = np.subtract(data[i], 1.0)
				data[i] = np.multiply(data[i], 2.0)
		yield data

def getConfident(preds):
	lessThanLB = [pred for pred in preds if pred < lb]
	greaterThanUB = [pred for pred in preds if pred > ub]
	if len(lessThanLB) != 0 and len(greaterThanUB) != 0:
		raise ValueError
	if len(lessThanLB) != 0:
		return min(lessThanLB)
	return max(greaterThanUB)

def kaggleTest(model, predict=True, write_csv=True, dog_probabs=None, img_side=img_width,
				inception=False):
	fnames = [TEST_DIR + fname for fname in listdir(TEST_DIR)]
	ids = [x[:-4] for x in [fname for fname in listdir(TEST_DIR)]]
	if predict:
		X = prep_data(fnames, img_side, img_side, inception=inception)
		i = 0
		saved = 50
		dog_probabs = []
		print 'Beginning prediction phase...'
		for mini_batch in X:
			y = dog_probab(model.predict(mini_batch))
			# for j, pred in enumerate(y):
			# 	# if pred < 0.3:
			# 	# 	y[j] = 0.
			# 	# if pred > 0.7:
			# 	# 	y[j] = 1.
			# 	# else:
			# 	# 	y[j] = 0.7
			# 	pass
			# 	# if doubtful(pred):
			# 	# 	zoomPreds = dog_probab(model.predict(getVariations(mini_batch[j]), 
			# 	# 					batch_size=mini_batch_sz))
			# 	# 	y[j] = min(y[j], min(zoomPreds)) if y[j] < lbub else max(y[j], max(zoomPreds))
			# 	#	saved -= 1
			# 	#	write_image(mini_batch[j], '../failures/{}.jpg'.format(ids[i + j]))
			# 	#	if saved == 0: return
			dog_probabs.extend(y)
			i += mini_batch_sz
			if i % 100 == 0: print "Finished {} of {}".format(i, len(fnames))

	if write_csv:
		with open(ROOT + '/out.csv','w') as f:
			f.write('id,label\n')
			for i,pred in zip(ids,dog_probabs):
				f.write('{},{}\n'.format(i,str(pred)))
	return dog_probabs

def ensemble():
	for fname in ['bestval{}.h5'.format(i) for i in xrange(4,5)]:
		model = load_model(fname)
		fnames = [VAL_DIR + 'cats/' + im for im in listdir(VAL_DIR + 'cats/')]
		fnames += [VAL_DIR + 'dogs/' + im for im in listdir(VAL_DIR + 'dogs/')]
		gen = prep_data(fnames, model.layers[0].input_shape[1], model.layers[0].input_shape[2])
		dog_probabs = []
		i = 0
		for mini_batch in gen:
			y = dog_probab(model.predict(mini_batch))
			dog_probabs.extend(y)
			i += mini_batch_sz
			if i % 100 == 0: print "Finished {} of {}".format(i, len(fnames))

		# out = model.predict_generator(gen, val_samples=len(fnames))
		pickle.dump(dog_probabs, open(ROOT + '/predictions/' + fname,'w'))
		print 'Done with ' + fname

def dumper(model,kind,fname=None):
	if not fname:
		fname = '{}/models/{}-{}.h5'.format(ROOT,
										str(datetime.now()).replace(' ','-'),kind)
	try:
		with open(fname,'w') as f:
			model.save(fname)
	except IOError:
		raise IOError('Unable to open: {}'.format(fname))
	return fname

# def random_bright_shift(image):
# 	print np.asarray(image,dtype=np.uint8)
# 	image = np.asarray(image,dtype=np.uint8)
# 	image1 = cv2.cvtColor(image,cv2.COLOR_RGB2HSV)
# 	random_bright = .25+np.random.uniform()
# 	image1[:,:,2] = image1[:,:,2]*random_bright
# 	image1 = cv2.cvtColor(image1,cv2.COLOR_HSV2RGB)
# 	return image1

def random_bright_shift(arr, tf):
	img = to_PIL(arr, tf)
	if tf: return ImageEnhance.Brightness(img).enhance(np.random.uniform(0.8, 1.2))
	return to_theano(ImageEnhance.Brightness(img).enhance(np.random.uniform(0.8, 1.2)))

def random_contrast_shift(arr, tf):
	img = to_PIL(arr, tf)
	if tf: return ImageEnhance.Contrast(img).enhance(np.random.uniform(0.8, 1.2))
	return to_theano(ImageEnhance.Contrast(img).enhance(np.random.uniform(0.8, 1.2)))

def blur(arr, tf):
	img = to_PIL(arr, tf)
	if tf: return img.filter(ImageFilter.BLUR)
	return to_theano(img.filter(ImageFilter.BLUR))