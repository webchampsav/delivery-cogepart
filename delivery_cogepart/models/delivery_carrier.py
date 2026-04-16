import requests
from odoo import models, fields, _
from odoo.exceptions import UserError


class ProviderCogepart(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('cogepart', 'Cogepart')],
        ondelete={'cogepart': 'set default'}
    )

    cogepart_login = fields.Char(string='Login API Cogepart')
    cogepart_password = fields.Char(string='Mot de passe API Cogepart')
    cogepart_siret = fields.Char(string='SIRET (identifiant client Cogepart)')
    cogepart_api_url = fields.Char(
        string='URL API',
        default='https://api.cogepart.fr/v1.0'
    )

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

        if response.status_code != 201:
            raise UserError(_(
                "Cogepart : authentification échouée.\n"
                "Vérifiez votre login et mot de passe API.\n"
                "Réponse serveur : %s"
            ) % response.text)

        return response.json()  # le token JWT brut

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

            # Payload minimum viable selon la doc Cogepart
            payload = {
                "client": {
                    "company": {
                        "identifierType": "SIRET",
                        "identifierValue": self.cogepart_siret or '',
                    }
                },
                "deliveryLocation": {
                    "address": {
                        "addresslineList": [
                            partner.street or '',
                            partner.street2 or '',
                        ],
                        "zipCode": partner.zip or '',
                        "city": partner.city or '',
                        "countryCode": partner.country_id.code or 'FR',
                    },
                    "entity": {
                        "person": {
                            "lastname": partner.name or '',
                            "firstname": '',
                        }
                    }
                },
                "dimensions": {
                    "itemCount": int(picking.shipping_weight) or 1
                },
                "customerReference": picking.name,
            }

            # Si le partenaire a nom + prénom séparés (contact individuel)
            if partner.is_company is False and ' ' in (partner.name or ''):
                parts = partner.name.split(' ', 1)
                payload["deliveryLocation"]["entity"]["person"] = {
                    "firstname": parts[0],
                    "lastname": parts[1],
                }

            url = f"{self.cogepart_api_url}/mission"
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=15)
            except requests.exceptions.RequestException as e:
                raise UserError(_("Cogepart : erreur réseau.\n%s") % str(e))

            if response.status_code != 201:
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
