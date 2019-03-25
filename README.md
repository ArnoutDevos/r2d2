# Meta-learning with differentiable closed-form solvers

This repo implements the paper "Meta-learning with differentiable closed-form solvers" [1] in TensorFlow. It builds on code from MAML ([link](https://github.com/cbfinn/maml)) [2].

### Dependencies
This code requires the following:
* python 2.\* or python 3.\*
* TensorFlow v1.0+

### Data
For the Omniglot, MiniImagenet and CIFAR-FS data, see the usage instructions in `data/omniglot_resized/resize_images.py` and `data/miniImagenet/proc_images.py` and `data/CIFARFS/get_cifarfs.py` respectively.

### Usage
To run the code, see the usage instructions at the top of `main.py`.

### Results

After around 20,000 (20k) iterations, with a 95% confidence interval:

| Dataset, method | this code<br />MAML model<br />accuracy | this code<br />R2D2 model<br />accuracy | reported by<br /> R2D2 [2] |
| ------------- | :---------------------: | :-----------: | :-----------: |
| CIFAR-FS, R2D2 5-way, 1-shot | 54.3 ± 1.8% | 62.7 ± 1.8% (11k) |65.3 ± 0.2% |
| CIFAR-FS, R2D2 5-way, 5-shot | 69.7 ± 0.9% | 75.1 ± 0.9% (18k) |79.4 ± 0.1% |
| CIFAR-FS, R2D2 2-way, 1-shot |  78.3 ± 2.8% | 87.3 ± 2.3% (60k) |83.4 ± 0.3% |
| CIFAR-FS, R2D2 2-way, 5-shot |  87.7 ± 1.1% | 90.7 ± 1.0% (60k) |91.1 ± 0.2% |
| miniImagenet, R2D2 5-way, 1-shot | 45.7 ± 1.8%  | 51.7 ± 1.8% | 51.5 ± 0.2%  |
| miniImagenet, R2D2 5-way, 5-shot | 63.7 ± 1.3%  | 63.3 ± 0.9% |68.8 ± 0.2%  |
| miniImagenet, R2D2 2-way, 1-shot | 74.7 ± 2.9% | 74.6 ± 2.9% | 76.7 ± 0.3%  |
| miniImagenet, R2D2 2-way, 5-shot | 83.0 ± 1.2% | 86.8 ± 1.1% | 86.8 ± 0.2%  |

### References

[1] Bertinetto, Luca, et al. "Meta-learning with differentiable closed-form solvers." *arXiv preprint arXiv:1805.08136* (2018).

[2] Finn, Chelsea, Pieter Abbeel, and Sergey Levine. "Model-agnostic meta-learning for fast adaptation of deep networks." *arXiv preprint arXiv:1703.03400* (2017).
7
