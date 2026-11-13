{
    description = "Flake for developing code for STM32 microchips";

    inputs = {
        nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-26.05";
        flake-parts.url = "github:hercules-ci/flake-parts";
    };

    outputs = { flake-parts, ...} @inputs:
        flake-parts.lib.mkFlake { inherit inputs; } {
            # Linux x86 and ARM as well as MacOS x86 and ARM
            systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
            perSystem = {pkgs, lib, ...}: 
            # prek inside an FHS env so downloaded binaries can run
            let prek-wrapped =
                if pkgs.stdenv.isLinux then
                    pkgs.buildFHSEnv {
                    name = "prek";
                    targetPkgs = p: [
                        p.prek
                        p.uv
                        p.git
                        p.zlib
                        p.stdenv.cc.cc.lib
                    ];
                    runScript = "prek";
                }
                else
                pkgs.prek; # macOS doesn't need a wrap

            in {
                devShells.default = pkgs.mkShell {
                    buildInputs = with pkgs; [
                        gcc-arm-embedded
                        openocd # Have openocd installed system-wide so it has the proper udev rules
                        stlink
                        cmake
                        ninja
                        can-utils
                        savvycan
                        clang
                        clang-tools
                        pkgs.pkgsCross.arm-embedded.buildPackages.gdb
                        prek-wrapped
                    ] ++ lib.optionals pkgs.stdenv.isDarwin [ pkgs.uv ];
                };    
            };
    };
}
