FROM ubuntu:latest

RUN apt-get update

# essential
RUN apt-get install -y \
  vim \
  git \
  build-essential \
  wget \
  curl \
  libcurl4-openssl-dev

RUN apt-get -y install \
  python3.6 \
  python3-dev \
  python3-distutils \
  python3-numpy \
  python3-scipy 
RUN wget https://bootstrap.pypa.io/get-pip.py
RUN python3.6 get-pip.py
RUN pip install jupyter

RUN pip install jupyter_contrib_nbextensions && \
  jupyter nbextensions_configurator enable --system && \
  mkdir -p $(jupyter --data-dir)/nbextensions && \
  cd $(jupyter --data-dir)/nbextensions && \
  git clone https://github.com/lambdalisue/jupyter-vim-binding vim_binding && \
  chmod -R go-w vim_binding && \
  jupyter nbextension enable vim_binding/vim_binding

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN apt-get install -y libglpk40 python3-swiglpk

