{
    'name': 'Cogepart Shipping Provider',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Intégration transporteur Cogepart via API REST',
    'author': 'Ton Nom',
    'depends': ['delivery', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/delivery_cogepart_view.xml',
        'data/delivery_cogepart.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
