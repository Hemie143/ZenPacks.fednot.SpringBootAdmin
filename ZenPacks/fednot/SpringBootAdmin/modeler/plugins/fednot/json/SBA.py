# stdlib Imports
import json
import re

# Twisted Imports
from twisted.internet.defer import inlineCallbacks, returnValue, DeferredSemaphore, DeferredList
from twisted.web.client import getPage

# Zenoss Imports
from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin
from Products.DataCollector.plugins.DataMaps import ObjectMap, RelationshipMap
from Products.ZenUtils.Utils import monkeypatch


# TODO : CamelCase (check in YAML)

class SBA(PythonPlugin):
    """
    Doc about this plugin
    """

    requiredProperties = (
        'zSpringBootPort',
        'zSpringBootURI',
        'zIVGroups',
        'zIVUser',
    )

    deviceProperties = PythonPlugin.deviceProperties + requiredProperties

    @staticmethod
    def add_tag(result, label):
        return tuple((label, result))

    @inlineCallbacks
    def collect(self, device, log):
        log.debug('{}: Modeling collect'.format(device.id))

        port = getattr(device, 'zSpringBootPort', None)
        uris = getattr(device, 'zSpringBootURI', None)
        log.debug('zSpringBootURI: {}'.format(uris))
        ivGroups = getattr(device, 'zIVGroups', None)
        ivUser = getattr(device, 'zIVUser', None)

        ip_address = device.manageIp
        if not ip_address:
            log.error("%s: IP Address cannot be empty", device.id)
            returnValue(None)

        deferreds = []
        sem = DeferredSemaphore(1)

        # TODO: remove loop
        for uri in uris:
            url = 'http://{}:{}/{}'.format(ip_address, port, uri)
            d = sem.run(getPage, url,
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "Mozilla/3.0Gold",
                            "iv-groups": ivGroups,
                            "iv-user": ivUser,
                        },
                        )
            context = uri.split('/')[0]
            d.addCallback(self.add_tag, context)
            deferreds.append(d)

        results = yield DeferredList(deferreds, consumeErrors=True)
        for success, result in results:
            if not success:
                log.error('{}: {}'.format(device.id, result.getErrorMessage()))

        returnValue(results)

    def process(self, device, results, log):
        """
        Must return one of :
            - None, changes nothing. Good in error cases.
            - A RelationshipMap, for the device to component information
            - An ObjectMap, for the device device information
            - A list of RelationshipMaps and ObjectMaps, both
        """
        # log.debug('SBA process results: {}'.format(results))

        result_data = {}
        for success, result in results:
            if success:
                if result:
                    content = json.loads(result[1])
                else:
                    content = {}
                result_data[result[0]] = content

        # sba_data = result_data.get('sba', '')
        log.debug('AAA result_data: {}'.format(result_data))

        sba_maps = []
        rm = []
        rm_sba = []
        rm_app = []
        rm_comp = []
        rm_jvm = []
        for context, sba_data in result_data.iteritems():
            # Modeling of SBA instances
            om_sba = ObjectMap()
            sba_label = 'Spring Boot Admin ({})'.format(context)
            om_sba.id = self.prepId('sba_{}'.format(context))
            om_sba.title = sba_label
            om_sba.context = context
            if 'endpoints' in sba_data[0]:
                om_sba.sbaVersion = '2'
            else:
                om_sba.sbaVersion = '1'
            sba_maps.append(om_sba)
            component_sba = 'springBootAdmins/{}'.format(om_sba.id)
            app_maps = []
            for app in sba_data:
                # Modeling of Applications
                if 'registration' not in app:
                    # Spring Boot Admin v1
                    app_info = app
                else:
                    # Spring Boot Admin v2
                    app_info = app.get('registration', '')
                om_app = ObjectMap()
                app_label = app_info.get('name', '')
                app_name = app_label.lower().replace(' ', '_')
                app_id = app.get('id', '')
                om_app.id = self.prepId('app_{}_{}'.format(app_name, app_id))
                om_app.applicationComponentID = om_app.id                   # to be inherited
                om_app.applicationName = app_label
                om_app.applicationNameID = self.prepId('{}_{}'.format(app_name, app_id))
                om_app.applicationID = app_id
                mgmtURL = app_info.get('managementUrl', '')
                om_app.mgmtURL = mgmtURL
                om_app.healthURL = app_info.get('healthUrl', '')
                om_app.serviceURL = app_info.get('serviceUrl', '')
                r = re.match(r'^(.*:)//([A-Za-z0-9\-\.]+)(:[0-9]+)?(.*)$', mgmtURL)
                server = r.group(2)
                om_app.hostingServer = server
                om_app.title = '{} on {} ({})'.format(app_label, server, app_id)
                app_maps.append(om_app)

                applicationNameID = '{}_{}'.format(app_label.lower().replace(' ', '_'), app_id)
                component_app = '{}/springBootApplications/{}'.format(component_sba, om_app.id)

                # Modeling of Application Components
                app_status = app.get('statusInfo', '')
                app_details = app_status.get('details', '')
                comp_maps = []
                for comp_name in app_details:
                    if comp_name == 'status':
                        continue
                    om_comp = ObjectMap()
                    om_comp.id = self.prepId('comp_{}_{}'.format(applicationNameID, comp_name))
                    om_comp.title = '{} ({} on {})'.format(comp_name, app_label, server)
                    om_comp.componentName = comp_name
                    comp_maps.append(om_comp)

                rm_comp.append(RelationshipMap(relname='springBootComponents',
                                               modname='ZenPacks.fednot.SpringBootAdmin.SpringBootComponent',
                                               compname=component_app,
                                               objmaps=comp_maps))

                # Modeling of Application JVM
                om_jvm = ObjectMap()
                om_jvm.id = self.prepId('jvm_{}'.format(applicationNameID))
                om_jvm.title = 'JVM ({} on {})'.format(app_label, server)
                if om_sba.sbaVersion == '1':
                    rm_jvm.append(RelationshipMap(relname='springBootJVMs',
                                                  modname='ZenPacks.fednot.SpringBootAdmin.SpringBootJVM',
                                                  compname=component_app,
                                                  objmaps=[om_jvm]))
                elif om_sba.sbaVersion == '2':
                    rm_jvm.append(RelationshipMap(relname='springBootJVM2s',
                                                  modname='ZenPacks.fednot.SpringBootAdmin.SpringBootJVM2',
                                                  compname=component_app,
                                                  objmaps=[om_jvm]))


            rm_app.append(RelationshipMap(relname='springBootApplications',
                                          modname='ZenPacks.fednot.SpringBootAdmin.SpringBootApplication',
                                          compname=component_sba,
                                          objmaps=app_maps))
        rm_sba.append(RelationshipMap(relname='springBootAdmins',
                                      modname='ZenPacks.fednot.SpringBootAdmin.SpringBootAdmin',
                                      compname='',
                                      objmaps=sba_maps))

        rm.extend(rm_sba)
        rm.extend(rm_app)
        rm.extend(rm_comp)
        rm.extend(rm_jvm)

        return rm
