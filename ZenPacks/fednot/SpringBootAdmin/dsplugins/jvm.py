# stdlib Imports
import json
import logging
import re
import datetime
import time
import base64
from operator import itemgetter

# Twisted Imports
from twisted.internet.defer import returnValue, DeferredSemaphore, DeferredList, inlineCallbacks
from twisted.web.client import getPage

# Zenoss imports
from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource import PythonDataSourcePlugin
from Products.ZenUtils.Utils import prepId

# Setup logging
log = logging.getLogger('zen.PythonSBAJVM')


class JVM(PythonDataSourcePlugin):
    proxy_attributes = (
        'zSpringBootPort',
        'zIVGroups',
        'zIVUser',
    )

    urls = {
        'jvm': '{}/management/metrics',
    }

    @staticmethod
    def add_tag(result, label):
        return tuple((label, result))

    # TODO: check config_key broker
    @classmethod
    def config_key(cls, datasource, context):
        log.debug('In config_key {} {} {} {}'.format(context.device().id, datasource.getCycleTime(context),
                                                    context.applicationName, 'SB_JVM'))
        return (
            context.device().id,
            datasource.getCycleTime(context),
            context.id,
            'SB_JVM'
        )

    @classmethod
    def params(cls, datasource, context):
        log.debug('Starting SBA JVM params')
        params = {}
        params['serviceURL'] = context.serviceURL
        params['applicationNameID'] = context.applicationNameID
        params['sbaVersion'] = context.sbaVersion
        log.debug('params is {}'.format(params))
        return params

    def collect(self, config):
        log.debug('Starting SBA JVM collect')
        # TODO : cleanup job collect

        ip_address = config.manageIp
        if not ip_address:
            log.error("%s: IP Address cannot be empty", device.id)
            returnValue(None)

        applicationList = []
        deferreds = []
        sem = DeferredSemaphore(1)
        for datasource in config.datasources:
            applicationNameID = datasource.params['applicationNameID']        # app_delivery_service_8df95ae5
            if applicationNameID in applicationList:
                continue
            applicationList.append(applicationNameID)
            serviceURL = datasource.params['serviceURL']
            sbaVersion = datasource.params['sbaVersion']

            url = self.urls[datasource.datasource].format(serviceURL)
            # TODO : move headers to Config properties
            d = sem.run(getPage, url,
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "Mozilla/3.0Gold",
                            "iv-groups": datasource.zIVGroups,
                            "iv-user": datasource.zIVUser,
                        },
                        )
            tag = '{}_{}'.format(datasource.datasource, applicationNameID)      # order_delivery_service_3db30547
            d.addCallback(self.add_tag, tag)
            deferreds.append(d)
        return DeferredList(deferreds)

    def onSuccess(self, result, config):
        log.debug('Success job - result is {}'.format(result))
        # TODO : cleanup job onSuccess

        data = self.new_data()

        ds_data = {}
        for success, ddata in result:
            if success:
                ds = ddata[0]
                metrics = json.loads(ddata[1])
                ds_data[ds] = metrics

        ds0 = config.datasources[0]
        componentID = prepId(ds0.component)
        applicationNameID = ds0.params['applicationNameID']
        tag = '{}_{}'.format(ds0.datasource, applicationNameID)
        jvm_data = ds_data.get(tag, '')
        if not jvm_data:
            # TODO: Add event: no data collected
            return data
        for point in ds0.points:
            if point.id in jvm_data:
                data['values'][componentID][point.id] = jvm_data[point.id]

        mem_used = jvm_data['mem'] - jvm_data['mem.free']
        data['values'][componentID]['mem.used'] = mem_used
        data['values'][componentID]['mem.used_percentage'] = float(mem_used) / float(jvm_data['mem']) * 100.0
        data['values'][componentID]['heap.used_percentage'] = float(jvm_data['heap.used']) / float(jvm_data['heap']) \
                                                              * 100.0
        log.debug('Success job - data is {}'.format(data))
        return data

    def onError(self, result, config):
        log.error('Error - result is {}'.format(result))
        # TODO: send event of collection failure
        return {}

class JVM2(PythonDataSourcePlugin):
    proxy_attributes = (
        'zSpringBootPort',
        'zIVGroups',
        'zIVUser',
    )

    urls = {
        'jvm': '{}/management/metrics',
    }

    metrics = {'mem': {'endpoint': 'jvm.memory.committed', 'stat': 'VALUE'},
               'mem.used': {'endpoint': 'jvm.memory.used', 'stat': 'VALUE'},
               'classes.loaded': {'endpoint': 'jvm.classes.loaded', 'stat': 'VALUE'},
               'classes.unloaded': {'endpoint': 'jvm.classes.unloaded', 'stat': 'COUNT'},
               'heap.committed': {'endpoint': 'jvm.memory.committed?tag=area:heap', 'stat': 'VALUE'},        # add tag
               'heap.used': {'endpoint': 'jvm.memory.used?tag=area:heap', 'stat': 'VALUE'},                  # add tag
               'process.cpu.usage': {'endpoint': 'process.cpu.usage', 'stat': 'VALUE'},
               'process.files.max': {'endpoint': 'process.files.max', 'stat': 'VALUE'},
               'process.files.open': {'endpoint': 'process.files.open', 'stat': 'VALUE'},
               'threads': {'endpoint': 'jvm.threads.live', 'stat': 'VALUE'},
                }

    @staticmethod
    def add_tag(result, label):
        return tuple((label, result))

    # TODO: check config_key broker
    @classmethod
    def config_key(cls, datasource, context):
        log.debug('In config_key {} {} {} {}'.format(context.device().id, datasource.getCycleTime(context),
                                                    context.applicationName, 'SB_JVM2'))
        return (
            context.device().id,
            datasource.getCycleTime(context),
            context.id,
            'SB_JVM2'
        )

    @classmethod
    def params(cls, datasource, context):
        log.debug('Starting SBA JVM params')
        params = {}
        params['serviceURL'] = context.serviceURL
        params['applicationNameID'] = context.applicationNameID
        log.debug('params is {}'.format(params))
        return params

    def collect(self, config):
        log.debug('Starting SBA JVM collect')
        # TODO : cleanup job collect

        ip_address = config.manageIp
        if not ip_address:
            log.error("%s: IP Address cannot be empty", device.id)
            returnValue(None)

        ds0 = config.datasources[0]
        applicationList = []
        deferreds = []
        sem = DeferredSemaphore(1)
        for metric, props in self.metrics.iteritems():
            applicationNameID = ds0.params['applicationNameID']        # app_delivery_service_8df95ae5
            # if applicationNameID in applicationList:
            #     continue
            # applicationList.append(applicationNameID)
            serviceURL = ds0.params['serviceURL']

            # url = self.urls[datasource.datasource].format(serviceURL)
            endpoint = props['endpoint']
            url = '{}/management/metrics/{}'.format(serviceURL, endpoint)
            log.debug('AAA url: {}'.format(url))

            d = sem.run(getPage, url,
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "Mozilla/3.0Gold",
                            "iv-groups": ds0.zIVGroups,
                            "iv-user": ds0.zIVUser,
                            },
                        )
            tag = 'jvm_{}_{}'.format(metric, applicationNameID)      # order_delivery_service_3db30547
            d.addCallback(self.add_tag, tag)
            deferreds.append(d)
        return DeferredList(deferreds)

    def onSuccess(self, result, config):
        log.debug('Success job - result is {}'.format(result))
        # TODO : cleanup job onSuccess

        data = self.new_data()
        ds_data = {}
        for success, ddata in result:
            if success:
                ds = ddata[0]
                metrics = json.loads(ddata[1])
                ds_data[ds] = metrics

        ds0 = config.datasources[0]
        applicationNameID = ds0.params['applicationNameID']
        componentID = prepId(ds0.component)

        for metric, props in self.metrics.iteritems():
            tag = 'jvm_{}_{}'.format(metric, applicationNameID)
            metric_data = ds_data.get(tag, '')
            log.debug('BBB metric_data: {}={}'.format(metric, metric_data))
            '''
            {u'measurements': [{u'value': 848392192.0, u'statistic': u'VALUE'}], u'name': u'jvm.memory.committed',
             u'availableTags': [{u'tag': u'area', u'values': [u'heap', u'nonheap']}, {u'tag': u'id',
                                                                                      u'values': [u'Par Survivor Space',
                                                                                                  u'Compressed Class Space',
                                                                                                  u'Metaspace',
                                                                                                  u'Code Cache',
                                                                                                  u'CMS Old Gen',
                                                                                                  u'Par Eden Space']}]}
            '''
            if not metric_data:
                # TODO: Add event: no data collected
                log.debug('BBB metric: {}'.format(metric))
                log.debug('BBB ds_data: {}'.format(ds_data))
                log.debug('BBB componentID: {}'.format(componentID))

                return data
            measurements = metric_data.get('measurements', '')
            log.debug('BBB measurements: {}={}'.format(metric, measurements))
            stat = props['stat']
            measure = filter(lambda measurements: measurements['statistic'] == stat, measurements)
            log.debug('BBB test: {}={}'.format(metric, measure))
            if measure:
                value = measure[0]['value']
                data['values'][componentID][metric] = value

        data['values'][componentID]['heap.used_percentage'] = 100 * data['values'][componentID]['heap.used'] /\
                                                                  data['values'][componentID]['heap.committed']
        data['values'][componentID]['mem.used_percentage'] = 100 * data['values'][componentID]['mem.used'] / \
                                                              data['values'][componentID]['mem']
        '''
        ds0 = config.datasources[0]
        componentID = prepId(ds0.component)
        applicationNameID = ds0.params['applicationNameID']
        tag = '{}_{}'.format(ds0.datasource, applicationNameID)
        jvm_data = ds_data.get(tag, '')
        for point in ds0.points:
            if point.id in jvm_data:
                data['values'][componentID][point.id] = jvm_data[point.id]

        mem_used = jvm_data['mem'] - jvm_data['mem.free']
        data['values'][componentID]['mem.used'] = mem_used
        data['values'][componentID]['mem.used_percentage'] = float(mem_used) / float(jvm_data['mem']) * 100.0
        data['values'][componentID]['heap.used_percentage'] = float(jvm_data['heap.used']) / float(jvm_data['heap']) \
                                                              * 100.0
        '''

        '''

        mem:
        rrdtype: GAUGE
        mem.free:
        rrdtype: GAUGE
        mem.used:
        rrdtype: GAUGE
        mem.used_percentage:
        rrdtype: GAUGE
        '''

        log.debug('Success job - data is {}'.format(data))

        return data

    def onError(self, result, config):
        log.error('Error - result is {}'.format(result))
        # TODO: send event of collection failure
        return {}
