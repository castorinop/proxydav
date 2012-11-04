# 
# Copyright (c) 2012 Pablo Castorino. 
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.
#
# Author: Pablo Castorino <castorinop@gmail.com>

import os.path
import urllib
import urllib2
import urlparse
import httplib

from trac.core import *
from trac.web.api import Request, IRequestHandler, HTTPNotFound, HTTPForbidden
from trac.mimeview.api import Context
from trac.web.chrome import INavigationContributor, ITemplateProvider
from trac.perm import IPermissionRequestor
from trac.config import Option
from trac.util.text import to_unicode
from trac.util.translation import _
from trac.versioncontrol.api import RepositoryManager

from trac.wiki.formatter import format_to_html

from genshi.builder import tag



class ProxyDavModule(Component):
    """ proxy dav trougth trac."""
    
    implements(IRequestHandler, INavigationContributor, IPermissionRequestor, ITemplateProvider)
    
    proxydav_url = Option('proxydav', 'url', doc='URL to proxydav')
        

    def removePrefix(self, str, prefix):
        return str[len(prefix):] if str.startswith(prefix) else str

    # IRequestHandler methods
    def match_request(self, req):
        return req.path_info.startswith('/dav')
        
    def process_request(self, req):
        CHUNK = 16 * 1024

        req.perm.assert_permission('PROXYDAV_PULL')

        # Check for no URL being configured
        if not self.proxydav_url:
            raise TracError('You must configure a URL in trac.ini')        

        self.urlp = urlparse.urlparse(self.proxydav_url)

        self.log.info('check-path %r', req.path_info)
        if req.path_info.endswith('/dav'):
          self.log.info('dont have a repo_lbl. forwarding to help')
          return self.help(req)


        if not self.is_repo(req):
          raise HTTPNotFound(_('%s: unknown repository') % self.get_repo_name(req))


        #FIXME: check authenticated
        if req.method in ['GET', 'POST', 'OPTIONS', 'PROPFIND'] :
          if not req.perm.has_permission('PROXYDAV_PULL'):
            raise HTTPForbidden(_('dont have permission for pull repository'))
        else:
          if not (req.perm.has_permission('PROXYDAV_PUSH') or req.perm.has_permission('PROXYDAV_ADMIN')):
            raise HTTPForbidden(_('dont have permission for push on this repository'))


        ''' works with repo_base/repo '''
        repo = self.get_repo(req)
        self.log.info('repo data  %r' % repo)       
        path = repo['dir'].split("/")
        #FIXME: if is a complex path (?)
        repo_path = path[len(path)-1]
        self.log.info('repo path  %r' % repo_path)
        repo_lbl  = self.get_repo_name(req)
        self.repo_host_git = self.urlp.hostname

        self.log.info('repo path  %r' % req.server_name)
        self.repo_host_trac = req.server_name
        self.repo_uri_git = '%s/%s' % (self.urlp.path, repo_path)
        self.repo_uri_trac = '%s/dav/%s' %(req.base_path, repo_lbl)
        self.log.info("git %r, trac %r", self.repo_uri_git, self.repo_uri_trac)
        
        urlf = None
        resp = 200
        head = {}       
        page = ''

        # Grab the page
        #if req.environ['QUERY_STRING']:
        #print req.get_full_url()
       
        self.suffix = self.removePrefix(req.path_info, '/dav');
        self.suffix = self.urlp.path + self.suffix.replace(repo_lbl, repo_path);
        self.log.info("req.path_info %r", self.suffix)

        self.log.info("req-uri %r", self.suffix)

        if req.method == 'GET' or req.method == 'PUT':
          self.data_passtrougth(req)
        else:
          self.data_proxy(req)

        self.log.info("====== done")
        return

        ''' Request To DAV '''
        self.log.info("req-host %r", self.urlp.hostname)
        rd = httplib.HTTPConnection(self.urlp.hostname)

        self.log.info("req-method %r", req.method)
        rd.putrequest(req.method, self.repo_uri_git)

        '''headers from Request '''
        for k, v in req._inheaders:
          if k != 'x-forwarded-for' and k != 'x-real-ip':
            if v.find(self.repo_uri_trac):
              v = v.replace(self.repo_uri_trac, self.repo_uri_git)
              
            rd.putheader(k, v)
            self.log.info("req-head %r => %r ", k,v)

#        override lentgh  
#        if req.get_header('Content-Length'):
#          self.log.info("req-head content-length %r => %r ", int(req.get_header('Content-Length')), bitdiff)
#          rd.putheader('content-length', int(req.get_header('Content-Length')) + bitdiff)

        rd.endheaders()

        ''' data from Request '''
        while True:
          chunk = req.read(CHUNK)
          if not chunk: break
          rd.send(chunk)

        ''' Response from DAV '''
        resp = rd.getresponse()
                
        ''' headers to Response '''
        for k, v in head.items():
          if isinstance(v, str):
            v = v.replace(self.repo_uri_git, self.repo_uri_trac)
          self.log.info("res-header %r, %r", k, v)
          req.send_header(k, v)
        
        req.end_headers()

        ''' data from Request '''
        while True:
          chunk = req.read(CHUNK)
          if not chunk: break
          req.write(chunk)

        return

        ''' data '''
        data = req.read()
        #FIXME: only with PUT method ?
        if req.method == 'PUT':
          data = data.encode('string_escape')
        #self.log.info("req-data %r", data)
        rd.add_data(data)

        try: 
          urlf = urllib2.urlopen(rd) 
          head = dict(urlf.info())
          page = urlf.read()
          if req.method != 'GET':
            page = page.encode('utf-8', 'ignore')
          resp = urlf.code

        except urllib2.URLError, e:
          self.log.info("url error %r, %r, %r", e.code, e.msg, e.filename)
          resp = e.code
          head = dict((k,v) for k,v in e.hdrs.items())
          page = e.msg
        
        self.log.info("req-response %r", resp)

        #FIXME: needs rewrite paths
        if req.method != 'GET':
          page = page.replace(self.repo_uri_git, self.repo_uri_trac)

 #       self.log.info("res-data %r", page)

        #FIXME: needs recalculate etag (?)


        '''send data'''

        '''update content-length'''        
        head['content-length'] = len(page)

        req.send_response(resp)
          
        for k, v in head.items():
          if isinstance(v, str):
            v = v.replace(self.repo_uri_git, self.repo_uri_trac)
          self.log.info("res-header %r, %r", k, v)
          req.send_header(k, v)
        
        req.end_headers()

        self.log.info("res-data %r", page)

        if isinstance(page, unicode): 
 	        page = page.encode('utf-8') 

        req.write(page)


    def data_passtrougth(self, req):      
      CHUNK = 16 * 1024
      ''' Request To DAV '''
      self.log.info("pass req-host %r", self.urlp.hostname)
      dav = httplib.HTTPConnection(self.urlp.hostname)

      self.log.info("pass req-method %r, %r", req.method, self.suffix)
      dav.putrequest(req.method, self.suffix)

      '''headers from Request '''
      for k, v in req._inheaders:
        if k != 'x-forwarded-for' and k != 'x-real-ip':
          if v.find(self.repo_uri_trac):
            v = v.replace(self.repo_uri_trac, self.repo_uri_git)
            v = v.replace(self.repo_host_git, self.repo_host_trac)
            
          dav.putheader(k, v)
          self.log.info("pass req-head %r => %r ", k,v)

      #override lentgh  
#      if req.get_header('Content-Length'):
#        self.log.info("req-head content-length %r => %r ", int(req.get_header('Content-Length')), bitdiff)
#        dav.putheader('content-length', int(req.get_header('Content-Length')) + bitdiff)

      dav.endheaders()

      ''' data from Request '''
      while True:
        chunk = req.read(CHUNK)
        if not chunk: break
        dav.send(chunk)

      ''' Response from DAV '''
      resp = dav.getresponse()

      code = resp.status
      self.log.info("pass resp %r ", code)
      req.send_response(code)

      ''' headers to Response '''
      for k, v in resp.getheaders():
        self.log.info("pass res-head-o %r, %r", k, v)
        if isinstance(v, str):
          v = v.replace(self.repo_uri_git, self.repo_uri_trac)
          v = v.replace(self.repo_host_git, self.repo_host_trac)
        self.log.info("pass res-head-f %r, %r", k, v)
        req.send_header(k, v)

      if not resp.getheader('content-length'):
#        self.log.info("req-head content-length %r => %r ", int(req.get_header('Content-Length')), bitdiff)
        req.send_header('content-length', 0)
      
      req.end_headers()

      ''' data from Request '''
      while True:
        chunk = resp.read(CHUNK)
        if not chunk: break
        req.write(chunk)

    def data_proxy(self, req):
      ''' Request To DAV '''

      self.log.info("prxy req-host %r", self.urlp.hostname)
      dav = httplib.HTTPConnection(self.urlp.hostname)

      self.log.info("prxy req-method %r, %r", req.method, self.suffix)
      dav.putrequest(req.method, self.suffix)

      page = req.read()
      page = page.replace(self.repo_uri_trac, self.repo_uri_git)
      page = page.replace(self.repo_host_trac, self.repo_host_git)

      
      '''headers from Request '''
      for k, v in req._inheaders:
        if k == 'content-length':
          v = str(len(page))
          self.log.info("prxy req-head content-length %r ", v)
          dav.putheader('content-length', v)
          continue;
        if k != 'x-forwarded-for' and k != 'x-real-ip':
          if v.find(self.repo_uri_trac):
            v = v.replace(self.repo_uri_trac, self.repo_uri_git)
            v = v.replace(self.repo_host_trac, self.repo_host_git)
          
          dav.putheader(k, v)
          self.log.info("prxy req-head %r => %r ", k,v)

      #override lentgh  
#      if req.get_header('content-length'):
#        v = str(len(page))
#        self.log.info("prxy req-head content-length %r => %r ", v)
#        dav.putheader('content-length', v)

      dav.endheaders()

      ''' data from Request '''
      dav.send(page)

      #self.log.info("prxy send %r ", page)
      ''' Response from DAV '''
      resp = dav.getresponse()

      code = resp.status
      page = resp.read()
      page = page.replace(self.repo_uri_git, self.repo_uri_trac)
      page = page.replace(self.repo_host_git, self.repo_host_trac)


      self.log.info("prxy resp %r ", code)
      #self.log.info("prxy resp %r ", page)
      
      if isinstance(page, unicode): 
 	        page = page.encode('utf-8') 
   
      req.send_response(code)
      ''' headers to Response '''
      for k, v in resp.getheaders():
        if k == "content-length":
          continue;
        if isinstance(v, str):
          v = v.replace(self.repo_uri_git, self.repo_uri_trac)
          v = v.replace(self.repo_host_git, self.repo_host_trac)
        self.log.info("prxy res-header %r, %r", k, v)
        req.send_header(k, v)
 #     if resp.getheader('content-length'):
      self.log.info("prxy res-head content-length %r ", len(page))
      req.send_header('content-length', len(page))

      
      req.end_headers()

      ''' data from Request '''
      req.write(page)


    def help(self, req):

        rm = RepositoryManager(self.env)
        all_repositories = rm.get_all_repositories()
        page = _('= Repositories =') + '\n'

        for reponame, repoinfo in all_repositories.iteritems():
          path = '%s/dav/%s' % (req.base_path, reponame)
          url = '%s://%s@%s:%s%s' % (req.scheme, req.remote_user, req.server_name, req.server_port, path)
          url = urlparse.urlparse(url)
          self.log.info('repo %r', repoinfo)
          page += ' == %s == \r\n {{{\n %s %s \n}}}\n\n' % (reponame, self.helper_vcs(repoinfo['type']), url.geturl())

        data = {
            'proxydav_title': _('Repo access'), 
            'proxydav_page': self.format_to_html(req, page)
        }
        return 'proxydav.html', data, None

    def format_to_html(self, req, page):
      context = Context.from_request(req)
      return format_to_html(self.env, context, page)

    def helper_vcs(self, typ):
      if (typ == 'bzr'):
        return 'bzr branch'    
      elif (typ == 'git'):
        return 'git clone'
      else:
        return 'svn checkout'

    def is_repo(self, req):
        repo = self.get_repo(req)
        self.log.info('repo %r', repo)
        if repo is None or len(repo) == 0:
          self.log.info('repo dont exist')
          return False
        return True

    def get_repo(self, req):
        reponame = self.get_repo_name(req)
        self.log.info('repo %r', reponame)
        rm = RepositoryManager(self.env)
        repoinfo = rm.get_all_repositories().get(reponame, {})
        return repoinfo

    def get_repo_name(self, req):
      try:
        return req.path_info.split('/')[2]
      except:
        return None

    # INavigationContributor methods
    def get_navigation_items(self, req):
        if 'PROXYDAV_PULL' in req.perm:
            yield 'mainnav', 'proxydav', tag.a(_('Repo access'),
                                             href=req.href.dav())
                                             
    def get_active_navigation_item(self, req):
        return 'proxydav'
        
    # IPermissionRequestor methods
    def get_permission_actions(self):
        actions = ['PROXYDAV_PULL', 'PROXYDAV_PUSH']
        return  actions + [('PROXYDAV_ADMIN', actions)]
        
#    # ITemplateProvider methods
#    def get_htdocs_dirs(self):
#        from pkg_resources import resource_filename
#        return [('proxydav', resource_filename(__name__, 'htdocs'))]
            
    def get_templates_dirs(self):
        from pkg_resources import resource_filename
        return [resource_filename(__name__, 'templates')]

#    # IPreferencePanelProvider methods
#    def get_preference_panels(self, req):
#        yield 'proxydav', _('ProxyDav')

#    def render_preference_panel(self, req, panel):
#        if req.method == 'POST':
#            chrome_enabled = 'chrome_enabled' in req.args
#            req.session['proxydav_chrome_enabled'] = chrome_enabled and '1' or '0'
#            req.redirect(req.href.prefs('proxydav'))

#        data = {
#            'chrome_enabled': req.session.get('proxydav_chrome_enabled', '0')
#        }
#        return 'prefs_proxydav.html', data
