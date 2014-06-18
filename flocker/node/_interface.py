from zope.interface import Interface

class IRoute(Interface):
    def create_for(node, app):
        pass

    def destroy():
        pass
