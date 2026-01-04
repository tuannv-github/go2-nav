#!/bin/bash

# Oh My Zsh installation script with plugins
# Based on: https://gist.github.com/n1snt/454b879b8f0b7995740ae04c5fb5b7df

set -e

echo "Installing ZSH and related packages..."
sudo apt update
sudo apt install -y zsh-autosuggestions zsh-syntax-highlighting zsh curl git

# Install Oh My ZSH
echo "Installing Oh My ZSH..."
if [ ! -d "$HOME/.oh-my-zsh" ]; then
    sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
else
    echo "Oh My Zsh is already installed, skipping..."
fi

# Install plugins
echo "Installing ZSH plugins..."

# autosuggestions plugin
if [ ! -d "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autosuggestions" ]; then
    git clone https://github.com/zsh-users/zsh-autosuggestions.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autosuggestions
    echo "✓ Installed zsh-autosuggestions"
else
    echo "✓ zsh-autosuggestions already installed"
fi

# zsh-syntax-highlighting plugin
if [ ! -d "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting" ]; then
    git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting
    echo "✓ Installed zsh-syntax-highlighting"
else
    echo "✓ zsh-syntax-highlighting already installed"
fi

# zsh-fast-syntax-highlighting plugin
if [ ! -d "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/fast-syntax-highlighting" ]; then
    git clone https://github.com/zdharma-continuum/fast-syntax-highlighting.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/fast-syntax-highlighting
    echo "✓ Installed fast-syntax-highlighting"
else
    echo "✓ fast-syntax-highlighting already installed"
fi

# zsh-autocomplete plugin
if [ ! -d "${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autocomplete" ]; then
    git clone --depth 1 -- https://github.com/marlonrichert/zsh-autocomplete.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autocomplete
    echo "✓ Installed zsh-autocomplete"
else
    echo "✓ zsh-autocomplete already installed"
fi

# Configure .zshrc
echo "Configuring .zshrc..."
ZSH_RC="$HOME/.zshrc"

if [ -f "$ZSH_RC" ]; then
    # Check if plugins are already configured
    if grep -q "plugins=(git zsh-autosuggestions zsh-syntax-highlighting fast-syntax-highlighting zsh-autocomplete)" "$ZSH_RC"; then
        echo "✓ Plugins already configured in .zshrc"
    else
        # Replace the plugins line
        if grep -q "^plugins=(git)" "$ZSH_RC"; then
            sed -i 's/^plugins=(git)/plugins=(git zsh-autosuggestions zsh-syntax-highlighting fast-syntax-highlighting zsh-autocomplete)/' "$ZSH_RC"
            echo "✓ Updated plugins in .zshrc"
        else
            # If plugins line doesn't exist or is different, add it
            if ! grep -q "^plugins=" "$ZSH_RC"; then
                # Find where to insert (usually after ZSH_THEME)
                if grep -q "^ZSH_THEME=" "$ZSH_RC"; then
                    sed -i '/^ZSH_THEME=/a plugins=(git zsh-autosuggestions zsh-syntax-highlighting fast-syntax-highlighting zsh-autocomplete)' "$ZSH_RC"
                    echo "✓ Added plugins to .zshrc"
                else
                    echo "plugins=(git zsh-autosuggestions zsh-syntax-highlighting fast-syntax-highlighting zsh-autocomplete)" >> "$ZSH_RC"
                    echo "✓ Added plugins to .zshrc"
                fi
            fi
        fi
    fi
else
    echo "Warning: .zshrc not found. Oh My Zsh should have created it."
fi

# Change default shell to zsh (if not already)
CURRENT_SHELL=$(basename "$SHELL")
if [ "$CURRENT_SHELL" != "zsh" ]; then
    echo "Changing default shell to ZSH..."
    ZSH_PATH=$(which zsh)
    if [ -n "$ZSH_PATH" ]; then
        chsh -s "$ZSH_PATH"
        echo "✓ Default shell changed to ZSH"
        echo "  Note: You may need to log out and log back in for this to take effect."
    else
        echo "Warning: Could not find zsh binary"
    fi
else
    echo "✓ ZSH is already your default shell"
fi

echo ""
echo "Installation completed!"
echo "To apply changes, run: source ~/.zshrc"
echo "Or restart your terminal."
