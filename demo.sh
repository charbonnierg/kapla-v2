#!/usr/bin/env bash

# COPY_FROM_USER="cbenavides"
# SKEL="/home/$COPY_FROM"

init-user() {
    cd
    cp -R $SKEL/.profile.d $HOME
    cp $SKEL/.profile $HOME
    cp $SKEL/.bashrc $HOME
    sudo cp -R $SKEL/.poshthemes/ $HOME
    sudo chown -R charbonnierg:charbonnierg $HOME
    sudo chown -R $COPY_FROM_USER:$COPY_FROM_USER $SKEL/.poshthemes/
    source $HOME/.profile
    ls --tree $HOME/.profile.d
}

init-projects() {
    mkdir -p $HOME/azdevops/QUARA
    mkdir -p $HOME/github/charbonnierg
    < /dev/zero ssh-keygen -q -N ""
    echo -e "Add this SSH key to Azure Devops"
    cat -p $HOME/.ssh/id_rsa.pub
    read  -n 1 -p "Press enter to continue" __continue__
    cd $HOME/github/charbonnierg/
    git clone https://github.com/charbonnierg/kapla-v2.git
    cd -
    cd $HOME/azdevops/QUARA
    git clone git@ssh.dev.azure.com:v3/QUARA/QUARA-Control%20Unit/quara-python
    cd -
}

install-projects() {
    python3 -m pip install --user -U pip setuptools wheel testresources
    python3 -m pip install --user -e  /home/charbonnierg/github/charbonnierg/kapla-v2/
    cd azdevops/QUARA
    git checkout wip/kapla_cli_v2_dirty
    k install --exclude-project quara-devops live-viz quara-rec-tools
}

install-azcli() {
    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
    az login
    az acr login --name quara
}

install-skopeo() {
    . /etc/os-release
    echo "deb https://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_${VERSION_ID}/ /" | sudo tee /etc/apt/sources.list.d/devel:kubic:libcontainers:stable.list
    curl -L https://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/stable/xUbuntu_${VERSION_ID}/Release.key | sudo apt-key add -
    sudo apt-get update
    sudo apt-get -y install skopeo
}

list-tags() {
    skopeo list-tags "docker://$1"
}

purge-images() {
    IMAGE="$1"  # Must be something like quara.azurecr.io/quara-services (without tag)
    EXPR="$2"  # dot must be escaped: "1\.2\.0-rc" 
    skopeo list-tags "docker://$1" | grep "$2" | cut -f1 -d "," | xargs -I % sh -c "echo \"Removing docker://$1:%\" && skopeo delete docker://$1:%";
}


init-buildkit() {
    docker buildx create --use
}
  
#   161  skopeo inspect docker://quara.azurecr.io/smartgloveml:kapla_cli_v2_dirty-3d9088ed
#   162  skopeo inspect docker://quara.azurecr.io/smartgloveml:quara-services
#   163  skopeo inspect docker://quara.azurecr.io/quara-services
#   164  skopeo list-tags docker://quara.azurecr.io/quara-services
#   165  skopeo delete docker://quara.azurecr.io/quara-services:1.0.0
#   166  skopeo delete docker://quara.azurecr.io/quara-services:v1.0.0rc49
#   167  skopeo delete docker://quara.azurecr.io/quara-services:v1.0.0rc48
#   168  skopeo delete docker://quara.azurecr.io/quara-services:v1.0.0rc47
#   169  skopeo delete docker://quara.azurecr.io/quara-services:1.4.0rc29
#   170  skopeo delete docker://quara.azurecr.io/quara-services:1.4.0rc25
#   171  skopeo delete docker://quara.azurecr.io/quara-services:1.3.0-rc.24
#   172  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0
#   173  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f0 -f ","
#   174  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f 0 -f ","
#   175  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f 0 -d ","
#   176  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d ","
#   177  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs kopeo delete docker://quara.azurecr.io/quara-services:{}
#   178  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs skopeo delete docker://quara.azurecr.io/quara-services:{}
#   179  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs skopeo delete docker://quara.azurecr.io/quara-services:$1
#   180  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs sh -c "skopeo delete docker://quara.azurecr.io/quara-services:$1"
#   181  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs sh -c "skopeo delete docker://quara.azurecr.io/quara-services:$1" {}
#   182  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs sh -c "skopeo delete docker://quara.azurecr.io/quara-services:$1" {} \;
#   183  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs sh -c "skopeo delete docker://quara.azurecr.io/quara-services:{} \";
#   184  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs sh -c "skopeo delete docker://quara.azurecr.io/quara-services:{}";
#   185  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs -I sh -c "skopeo delete docker://quara.azurecr.io/quara-services:$1";
#   186  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs -I % sh -c "skopeo delete docker://quara.azurecr.io/quara-services:%";
#   187  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs -I % sh -c "echo -e 'Removing %' && skopeo delete docker://quara.azurecr.io/quara-services:%";
#   188  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.0 | cut -f1 -d "," | xargs -I % sh -c "echo 'Removing %' && skopeo delete docker://quara.azurecr.io/quara-services:%";
#   189  skopeo list-tags docker://quara.azurecr.io/quara-services | grep 1.0.1 | cut -f1 -d "," | xargs -I % sh -c "echo 'Removing %' && skopeo delete docker://quara.azurecr.io/quara-services:%";
#   191  skopeo list-tags docker://quara.azurecr.io/quara-services | grep "1.0.1" | cut -f1 -d "," | xargs -I % sh -c "echo 'Removing %' && skopeo delete docker://quara.azurecr.io/quara-services:%";
#   195  skopeo list-tags docker://quara.azurecr.io/quara-services | grep "1\.1\.0" | cut -f1 -d "," | xargs -I % sh -c "echo 'Removing %' && skopeo delete docker://quara.azurecr.io/quara-services:%";
#   197  skopeo list-tags docker://quara.azurecr.io/quara-services | grep "1\.2\.0-rc" | cut -f1 -d "," | xargs -I % sh -c "echo 'Removing docker://quara.azurecr.io/quara-services:%' && skopeo delete docker://quara.azurecr.io/quara-services:%";
#   199  skopeo inspect docker://quara.azurecr.io/smartgloveml
#   200  skopeo list-tags docker://quara.azurecr.io/smartgloveml
#   201  skopeo inspect docker://quara.azurecr.io/smartgloveml:kapla_cli_v2_dirty-3d9088ed
#   203  docker pull quara.azurecr.io/smartgloveml:kapla_cli_v2_dirty-3d9088ed
#   215  docker history quara.azurecr.io/smartgloveml:kapla_cli_v2_dirty-3d9088ed
#   221  skopeo sync --src docker quara.azurecr.io/smartgloveml:kapla_cli_v2_dirty-3d9088ed --dest dir smartgloveml:kapla_cli_v2_dirty-3d9088ed
#   224  cd smartgloveml\:kapla_cli_v2_dirty-3d9088ed/
#   226  cd smartgloveml\:kapla_cli_v2_dirty-3d9088ed/
#   235  cat manifest.json
#   242  tar -xf e7f446c57dbdedff53c177991d484f1c4486a7345edf6ba38d9a4737646cbf3a --one-top-level=last_layer
