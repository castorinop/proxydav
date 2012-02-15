#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

setup(
    name = 'TracProxyDav',
    version = '0.1',
    packages = ['proxydav'],
    package_data = { 'proxydav': ['templates/*.html', 'htdocs/*.js', 'htdocs/*.css' ] },

    author = 'Pablo Castorino',
    author_email = 'castorinop@gmail.com',
    description = 'A dav proxy with control access using trac permissions.',
    license = 'BSD',
    keywords = 'trac plugin',
    url = 'http://trac-hacks.org/wiki/Davprx-Plugin',
    classifiers = [
        'Framework :: Trac',
    ],
    
    install_requires = ['Trac'],

    entry_points = {
        'trac.plugins': [
            'proxydav.web_ui = proxydav.web_ui',
        ]
    },
)
