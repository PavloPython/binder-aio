#!/usr/bin/env python
# -*- coding: utf-8 -*-
# :noTabs=true:

# (c) Copyright Rosetta Commons Member Institutions.
# (c) This file is part of the Rosetta software suite and is made available under license.
# (c) The Rosetta software is developed by the contributing members of the Rosetta Commons.
# (c) For more information, see http://www.rosettacommons.org. Questions about this can be
# (c) addressed to University of Washington CoMotion, email: license@uw.edu.

## @file   build.py
## @brief  Script to build Binder
## @author Sergey Lyskov

from __future__ import print_function

import os, sys, argparse, platform, subprocess, imp, shutil, distutils.dir_util

from collections import OrderedDict

if sys.platform.startswith("linux"): Platform = "linux" # can be linux1, linux2, etc
elif sys.platform == "darwin" : Platform = "macos"
elif sys.platform == "cygwin" : Platform = "cygwin"
elif sys.platform == "win32" : Platform = "windows"
else: Platform = "unknown"
PlatformBits = platform.architecture()[0][:2]

_python_version_ = '{}.{}'.format(sys.version_info.major, sys.version_info.minor)  # should be formatted: 2.7 or 3.5

_pybind11_version_ = '1ee4128cfe8efcab618a980649cad9d830d8b32b'


def execute(message, command_line, return_='status', until_successes=False, terminate_on_failure=True, silent=False):
    print(message);  print(command_line)
    while True:

        p = subprocess.Popen(command_line, bufsize=0, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, errors = p.communicate()

        output = output + errors

        if sys.version_info[0] == 2: output = output.decode('utf-8', errors='replace').encode('utf-8', 'replace') # Python-2
        else: output = output.decode('utf-8', errors='replace')  # Python-3

        exit_code = p.returncode

        if exit_code  or  not silent: print(output)

        if exit_code and until_successes: pass  # Thats right - redability COUNT!
        else: break

        print( "Error while executing {}: {}\n".format(message, output) )
        print("Sleeping 60s... then I will retry...")
        time.sleep(60)

    if return_ == 'tuple': return(exit_code, output)

    if exit_code and terminate_on_failure:
        print("\nEncounter error while executing: " + command_line)
        if return_==True: return True
        else: print("\nEncounter error while executing: " + command_line + '\n' + output); sys.exit(1)

    if return_ == 'output': return output
    else: return False


def update_source_file(file_name, data):
    ''' write data to a file but only if file does not exist or it content different from data '''
    if( not os.path.isfile(file_name)  or  open(file_name).read() != data ):
        print('Writing '+ file_name)
        with open(file_name, 'w') as f: f.write(data)


def get_compiler_family():
    ''' Try to guess compiler family using Options.compiler '''
    if 'clang' in Options.compiler: return 'clang'
    if 'gcc'   in Options.compiler: return 'gcc'
    if 'cl'    in Options.compiler: return 'cl'
    return 'unknown'


def install_llvm_tool(name, source_location, prefix, debug, jobs=1, clean=True):
    ''' Install and update (if needed) custom LLVM tool at given prefix (from config).
        Return absolute path to executable on success and terminate with error on failure
    '''
    release = 'release_40'
    prefix += '/llvm-4.0'

    git_checkout = '( git checkout {0} && git reset --hard {0} )'.format(release) if clean else 'git checkout {}'.format(release)

    if not os.path.isdir(prefix): os.makedirs(prefix)

    if not os.path.isdir(prefix+'/llvm'): execute('Clonning llvm...', 'cd {} && git clone http://llvm.org/git/llvm.git llvm'.format(prefix) )
    execute('Checking out LLVM revision: {}...'.format(release), 'cd {prefix}/llvm && ( {git_checkout} || ( git fetch && {git_checkout} ) )'.format(prefix=prefix, git_checkout=git_checkout) )

    if not os.path.isdir(prefix+'/llvm/tools/clang'): execute('Clonning clang...', 'cd {}/llvm/tools && git clone http://llvm.org/git/clang.git clang'.format(prefix) )
    execute('Checking out Clang revision: {}...'.format(release), 'cd {prefix}/llvm/tools/clang && ( {git_checkout} || ( git fetch && {git_checkout} ) )'.format(prefix=prefix, git_checkout=git_checkout) )

    if not os.path.isdir(prefix+'/llvm/tools/clang/tools/extra'): execute('Clonning clang...', 'cd {}/llvm/tools/clang/tools && git clone http://llvm.org/git/clang-tools-extra.git extra'.format(prefix) )
    execute('Checking out Clang-tools revision: {}...'.format(release), 'cd {prefix}/llvm/tools/clang/tools/extra && ( {git_checkout} || ( git fetch && {git_checkout} ) )'.format(prefix=prefix, git_checkout=git_checkout) )

    tool_link_path = '{prefix}/llvm/tools/clang/tools/extra/{name}'.format(prefix=prefix, name=name)
    if os.path.islink(tool_link_path): os.unlink(tool_link_path)
    os.symlink(source_location, tool_link_path)

    cmake_lists = prefix + '/llvm/tools/clang/tools/extra/CMakeLists.txt'
    tool_build_line = 'add_subdirectory({})'.format(name)

    for line in open(cmake_lists):
        if line == tool_build_line: break
    else:
        with open(cmake_lists, 'w') as f: f.write( open(cmake_lists).read() + tool_build_line + '\n' )

    build_dir = prefix+'/llvm/build_' + release + '.' + Platform + ('.debug' if debug else '.release')
    if not os.path.isdir(build_dir): os.makedirs(build_dir)
    execute('Building tool: {}...'.format(name), 'cd {build_dir} && cmake -G Ninja -DCMAKE_BUILD_TYPE={build_type} -DLLVM_ENABLE_EH=1 -DLLVM_ENABLE_RTTI=ON .. && ninja -j{jobs}'.format(build_dir=build_dir, jobs=jobs, build_type='Debug' if debug else 'Release'), silent=True)
    print()

    executable = build_dir + '/bin/' + name
    if not os.path.isfile(executable): print("\nEncounter error while running install_llvm_tool: Build is complete but executable {} is not there!!!".format(executable) ); sys.exit(1)

    return executable


def install_pybind11(prefix, clean=True):
    ''' Download and install PyBind11 library at given prefix. Install version specified by _pybind11_version_ sha1
    '''
    #git_checkout = '( git fetch && git checkout {0} && git reset --hard {0} && git pull )'.format(_pybind11_version_) if clean else 'git checkout {}'.format(_pybind11_version_)
    git_checkout = '( git fetch && git reset --hard {0} )'.format(_pybind11_version_) if clean else 'git checkout {}'.format(_pybind11_version_)

    if not os.path.isdir(prefix): os.makedirs(prefix)
    package_dir = prefix + '/pybind11'

    if not os.path.isdir(package_dir): execute('Clonning pybind11...', 'cd {} && git clone https://github.com/RosettaCommons/pybind11.git'.format(prefix) )
    execute('Checking out PyBind11 revision: {}...'.format(_pybind11_version_), 'cd {package_dir} && ( {git_checkout} )'.format(package_dir=package_dir, git_checkout=git_checkout), silent=True)
    print()

    include = package_dir + '/include/pybind11/pybind11.h'
    if not os.path.isfile(include): print("\nEncounter error while running install_pybind11: Install is complete but include file {} is not there!!!".format(include) ); sys.exit(1)

    return package_dir + '/include'


def main(args):
    ''' Binding demo build/test script '''

    parser = argparse.ArgumentParser()

    parser.add_argument('-j', '--jobs', default=1, type=int, help="Number of processors to use on when building. (default: use all avaliable memory)")
    parser.add_argument("--type", default='Release', choices=['Release', 'Debug', 'MinSizeRel', 'RelWithDebInfo'], help="Specify build type")
    parser.add_argument('--compiler', default='clang', help='Compiler to use, defualt is clang')
    parser.add_argument('--binder', default='', help='Path to Binder tool. If none is given then download, build and install binder into main/source/build. Use "--binder-debug" to control which mode of binder (debug/release) is used.')
    parser.add_argument("--binder-debug", action="store_true", help="Run binder tool in debug mode (only relevant if no '--binder' option was specified)")
    parser.add_argument('--pybind11', default='', help='Path to pybind11 source tree')
    parser.add_argument('--annotate-includes', action="store_true", help='Annotate includes in generated source files')
    parser.add_argument('--trace', action="store_true", help='Binder will add trace output to to generated source files')

    global Options
    Options = parser.parse_args()

    source_path = os.path.abspath('.')

    if not Options.binder: Options.binder = install_llvm_tool__('binder', source_path+'/source', source_path + '/build', Options.binder_debug, jobs=Options.jobs)

    if not Options.pybind11: Options.pybind11 = install_pybind11(source_path + '/build')

    print( 'Binder binaries now ready at: {}\n{Pybind11 clone is ready at: {}'.format(Options.binder, Options.pybind11) )


if __name__ == "__main__":
    main(sys.argv)
