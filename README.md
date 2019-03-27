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

After 60,000 (60k) iterations, with a 95% confidence interval:

| Dataset, method | this code<br />MAML model<br />accuracy | this code<br />R2D2 model<br />accuracy | reported by<br /> R2D2 [2] |
| ------------- | :---------------------: | :-----------: | :-----------: |
| CIFAR-FS, R2D2 5-way, 1-shot | 57.0 ± 1.7% | 62.7 ± 1.8% (60k) |65.3 ± 0.2% |
| CIFAR-FS, R2D2 5-way, 5-shot | 68.9 ± 0.9% | 75.1 ± 0.9% (60k) |79.4 ± 0.1% |
| CIFAR-FS, R2D2 2-way, 1-shot |  82.4 ± 2.6% | 87.3 ± 2.3% (60k) |83.4 ± 0.3% |
| CIFAR-FS, R2D2 2-way, 5-shot |  88.0 ± 1.1% | 90.7 ± 1.0% (60k) |91.1 ± 0.2% |
| miniImagenet, R2D2 5-way, 1-shot | 48.1 ± 1.8%  | 51.7 ± 1.8% (60k) | 51.5 ± 0.2%  |
| miniImagenet, R2D2 5-way, 5-shot | 63.1 ± 0.9%  | 66.2 ± 0.9% (60k) |68.8 ± 0.2%  |
| miniImagenet, R2D2 2-way, 1-shot | 77.3 ± 2.8% | 79.5 ± 2.6% (60k) | 76.7 ± 0.3%  |
| miniImagenet, R2D2 2-way, 5-shot | 85.4 ± 1.1% | 87.3 ± 1.1% (60k) | 86.8 ± 0.2%  |

### References

[1] Bertinetto, Luca, et al. "Meta-learning with differentiable closed-form solvers." *arXiv preprint arXiv:1805.08136* (2018).

[2] Finn, Chelsea, Pieter Abbeel, and Sergey Levine. "Model-agnostic meta-learning for fast adaptation of deep networks." *arXiv preprint arXiv:1703.03400* (2017).
7
