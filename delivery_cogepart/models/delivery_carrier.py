import requests
import logging
from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProviderCogepart(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('cogepart', 'Cogepart')],
        ondelete={'cogepart': 'set default'}
    )

    cogepart_login = fields.Char(string='Login API Cogepart')
    cogepart_password = fields.Char(string='Mot de passe API Cogepart')
    cogepart_api_url = fields.Char(
        string='URL API',
        default='https://api.cogepart.fr/v1.0'
    )

    # Adresse d'enlèvement fixe (entrepôt Champs & Saveurs)
    cogepart_pickup_name = fields.Char(string='Nom contact enlèvement')
    cogepart_pickup_phone = fields.Char(string='Téléphone enlèvement')
    cogepart_pickup_street = fields.Char(string='Adresse enlèvement')
    cogepart_pickup_zip = fields.Char(string='Code postal enlèvement')
    cogepart_pickup_city = fields.Char(string='Ville enlèvement')

    # --------------------------------------------------
    # 1. Authentification → récupère le token JWT
    # --------------------------------------------------
    def _cogepart_get_token(self):
        url = f"{self.cogepart_api_url}/auth/login"
        payload = {
            "login": self.cogepart_login,
            "password": self.cogepart_password,
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
        except requests.exceptions.RequestException as e:
            raise UserError(_("Cogepart : impossible de joindre l'API.\n%s") % str(e))

        if response.status_code not in (200, 201):
            raise UserError(_(
                "Cogepart : authentification échouée.\n"
                "Vérifiez votre login et mot de passe API.\n"
                "Réponse serveur : %s"
            ) % response.text)

        return response.text.strip('"')

    # --------------------------------------------------
    # 2. Envoi de la commande → création d'une mission
    # --------------------------------------------------
    def cogepart_send_shipping(self, pickings):
        res = []
        for picking in pickings:
            token = self._cogepart_get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            partner = picking.partner_id

            # Construction de la liste des colis depuis les mouvements de stock
            parcel_list = []
            for move_line in picking.move_line_ids:
                barcode = (
                    move_line.lot_id.name
                    or move_line.product_id.barcode
                    or move_line.product_id.default_code
                    or f"REF-{picking.name}-{move_line.id}"
                )
                weight = move_line.product_id.weight or 1.0
                parcel_list.append({
                    "dimensions": {
                        "weight": {
                            "unit": "kg",
                            "value": str(weight)
                        }
                    },
                    "barcode": barcode
                })

            # Si aucun colis trouvé, on met un colis générique
            if not parcel_list:
                parcel_list = [{
                    "dimensions": {
                        "weight": {
                            "unit": "kg",
                            "value": str(picking.shipping_weight or 1.0)
                        }
                    },
                    "barcode": f"REF-{picking.name}"
                }]

            # Poids total
            total_weight = sum(
                float(p["dimensions"]["weight"]["value"]) for p in parcel_list
            )

            # Téléphone et email du destinataire
            phone_list = []
            if partner.phone:
                phone_list.append({"value": partner.phone})
            if partner.mobile:
                phone_list.append({"value": partner.mobile})

            email_list = []
            if partner.email:
                email_list.append({"value": partner.email})

            payload = {
                "externalReference": {
                    "value": picking.name
                },
                "deliveryLocation": {
                    "address": {
                        "addresslineList": [
                            partner.street or '',
                            partner.street2 or '',
                        ],
                        "city": partner.city or '',
                        "zipCode": partner.zip or '',
                        "countryCode": partner.country_id.code or 'FR',
                    },
                    "entity": {
                        "person": {
                            "lastname": partner.name or '',
                        },
                        "company": {
                            "name": partner.commercial_company_name or ''
                        },
                        "phoneList": phone_list,
                        "emailList": email_list,
                    }
                },
                "pickupLocation": {
                    "address": {
                        "addresslineList": [
                            self.cogepart_pickup_street or ''
                        ],
                        "city": self.cogepart_pickup_city or '',
                        "zipCode": self.cogepart_pickup_zip or '',
                        "countryCode": "FR"
                    },
                    "entity": {
                        "person": {
                            "lastname": self.cogepart_pickup_name or ''
                        },
                        "phoneList": [
                            {"value": self.cogepart_pickup_phone or ''}
                        ]
                    }
                },
                "dimensions": {
                    "weight": {
                        "unit": "kg",
                        "value": str(total_weight)
                    }
                },
                "parcelList": parcel_list
            }

            _logger.warning("COGEPART PAYLOAD: %s", payload)

            url = f"{self.cogepart_api_url}/mission"
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=15)
            except requests.exceptions.RequestException as e:
                raise UserError(_("Cogepart : erreur réseau.\n%s") % str(e))

            if response.status_code not in (200, 201):
                raise UserError(_(
                    "Cogepart : erreur lors de l'envoi de %s.\n"
                    "Réponse serveur : %s"
                ) % (picking.name, response.text))

            data = response.json()
            mission_id = str(data.get('id', ''))

            res.append({
                'exact_price': 0.0,
                'tracking_number': mission_id,
            })
        return res

    # --------------------------------------------------
    # 3. Lien de suivi
    # --------------------------------------------------
    def cogepart_get_tracking_link(self, picking):
        return (
            f"https://api.cogepart.fr/v1.0/label/mission/"
            f"{picking.carrier_tracking_ref}/single/pdf"
        )

    # --------------------------------------------------
    # 4. Annulation (non disponible pour l'instant)
    # --------------------------------------------------
    def cogepart_cancel_shipment(self, pickings):
        raise UserError(_(
            "L'annulation via API n'est pas encore implémentée pour Cogepart."
        ))
